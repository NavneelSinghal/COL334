import socket
import hashlib
import collections
import threading
import sys
import csv
import time

import matplotlib.pyplot as plt

'''
HTTP/1.1 206 Partial Content
Date: Wed, 18 Nov 2020 06:30:10 GMT
Server: Apache/2.4.29 (Ubuntu)
Last-Modified: Mon, 22 Apr 2019 17:44:41 GMT
ETag: "63025a-5872205e3b440"
Accept-Ranges: bytes
Content-Length: 100
Vary: Accept-Encoding
Content-Range: bytes 0-99/6488666
Keep-Alive: timeout=5, max=100
Connection: Keep-Alive
Content-Type: text/plain

'''

def parseCompletely(clientSocket):

    # parse till we get 2 \r\n in a row
    messageSize = int(1e9)
    headerSoFar = bytearray(b'')
    messageSoFar = bytearray(b'')
    state = 0 # 0 if inside header and 1 if in body

    while len(messageSoFar) < messageSize:

        receivedMessage = clientSocket.recv(1024)

        if receivedMessage == b'':
            raise RuntimeError('Broken connection')

        if state == 0:

            headerSoFar += bytearray(receivedMessage)
            pos = headerSoFar.find(b'\r\n\r\n')

            if pos != -1:

                messageSoFar = headerSoFar[pos + 4:]
                headerSoFar = headerSoFar[:pos + 4].decode('ASCII')

                lengthKeyPosition = headerSoFar.find('Content-Length: ')
                assert lengthKeyPosition != -1

                startValuePosition = lengthKeyPosition + len('Content-Length: ')
                endValuePosition = startValuePosition

                while headerSoFar[endValuePosition] != '\r':
                    endValuePosition += 1

                messageSize = int(headerSoFar[startValuePosition : endValuePosition])
                state = 1
                headerSoFar = bytearray(b'')

        else:

            messageSoFar += bytearray(receivedMessage)

    return messageSoFar

def downloadAtOnce():

    serverName = 'vayu.iitd.ac.in'
    serverPort = 80
    message = "GET /big.txt HTTP/1.1\r\nHost: vayu.iitd.ac.in\r\nConnection: keep-alive\r\n\r\n".encode('ASCII')

    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    clientSocket.connect((serverName, serverPort))
    clientSocket.send(message)

    receivedMessage = parseCompletely(clientSocket)

    clientSocket.close()

    hashValue = hashlib.md5(bytes(receivedMessage)).hexdigest()
    assert hashValue == '70a4b9f4707d258f559f91615297a3ec'

    #print(receivedMessage.decode('ASCII'))

def downloadChunkWise():

    serverName = 'vayu.iitd.ac.in'
    serverPort = 80
    message = "GET /big.txt HTTP/1.1\r\nHost: vayu.iitd.ac.in\r\nConnection: keep-alive\r\nRange: bytes="
    messageEnd = "\r\n\r\n"

    chunkSize = 1024 * 16
    fileSize = 6488666

    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    clientSocket.connect((serverName, serverPort))

    receivedMessage = bytearray(b'')

    missed = 0

    for currentPtr in range(0, fileSize, chunkSize):

        sendMessage = message + str(currentPtr) + '-' + str(min(currentPtr + chunkSize, fileSize) - 1) + messageEnd
        clientSocket.send((sendMessage).encode('ASCII'))

        while True:
            try:
                x = parseCompletely(clientSocket)
                #print(x.decode('ASCII'))
                receivedMessage += x
                break
            except:
                missed += 1
                clientSocket.close()
                clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                clientSocket.connect((serverName, serverPort))
                sendMessage = message + str(currentPtr) + '-' + str(min(currentPtr + chunkSize, fileSize) - 1) + messageEnd
                clientSocket.send((sendMessage).encode('ASCII'))

    clientSocket.close()

    hashValue = hashlib.md5(bytes(receivedMessage)).hexdigest()
    assert hashValue == '70a4b9f4707d258f559f91615297a3ec'

    #print(receivedMessage.decode('ASCII'))

def downloadPipelined():

    serverName = 'vayu.iitd.ac.in'
    serverPort = 80
    message = "GET /big.txt HTTP/1.1\r\nHost: vayu.iitd.ac.in\r\nConnection: keep-alive\r\nRange: bytes="
    messageEnd = "\r\n\r\n"

    fileSize = 6488666
    chunkSize = 1024 * 16 # 16 KB

    pipelineSize = 10

    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    clientSocket.connect((serverName, serverPort))

    receivedMessage = bytearray(b'')

    chunkSet = collections.OrderedDict()
    totalChunks = 0

    for currentPtr in range(0, fileSize, chunkSize):
        chunkSet[(currentPtr, min(currentPtr + chunkSize, fileSize) - 1)] = None
        totalChunks += 1

    d = dict() # mapping from chunk ranges to chunks

    currentChunkRange = None # a pair of integers determining the chunk
    messageSoFar = bytearray(b'')
    headerSoFar = bytearray(b'')
    state = 0 # 0 for inside header and 1 for inside message
    messageSize = int(1e9) # total message size - whenever the state is 0, change it to 1e9
    completeChunks = 0 # whenever we read a chunk completely, add it to the dictionary and increment this variable by 1
    currentlyParsing = False
    totalRightNow = 0

    received = min(totalChunks, pipelineSize)

    while completeChunks < totalChunks:

        while not currentlyParsing:
            try:
                if received == min(totalChunks - completeChunks, pipelineSize):
                    received = 0
                    sent = 0
                    for (begin, end) in chunkSet:
                        sendMessage = message + str(begin) + '-' + str(end) + messageEnd
                        clientSocket.send((sendMessage).encode('ASCII'))
                        sent += 1
                        if sent == pipelineSize:
                            break

                receivedMessage = bytearray(clientSocket.recv(1024))

                if receivedMessage == bytearray(b''):
                    raise RuntimeError('Broken connection')

                currentlyParsing = True

            except:

                currentChunkRange = None
                messageSoFar = bytearray(b'')
                headerSoFar = bytearray(b'')
                state = 0
                messageSize = int(1e9)

                clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                clientSocket.connect((serverName, serverPort))

                sent = 0
                for (begin, end) in chunkSet:
                    sendMessage = message + str(begin) + '-' + str(end) + messageEnd
                    clientSocket.send((sendMessage).encode('ASCII'))
                    sent += 1
                    if sent == pipelineSize:
                        break

        # now we are currently parsing
        if state == 0:

            assert len(receivedMessage) != 0
            headerSoFar += receivedMessage
            pos = headerSoFar.find(b'\r\n\r\n')

            if pos != -1:

                receivedMessage = headerSoFar[pos + 4:]
                headerSoFar = headerSoFar[:pos + 4].decode('ASCII')
                lengthKeyPosition = headerSoFar.find('Content-Length: ')
                assert lengthKeyPosition != -1
                startValuePosition = lengthKeyPosition + len('Content-Length: ')
                endValuePosition = startValuePosition
                while headerSoFar[endValuePosition] != '\r':
                    endValuePosition += 1
                messageSize = int(headerSoFar[startValuePosition : endValuePosition])
                rangeKeyPosition = headerSoFar.find('Content-Range: bytes ')
                assert rangeKeyPosition != -1
                startValuePosition = rangeKeyPosition + len('Content-Range: bytes ')
                endValuePosition = startValuePosition
                while headerSoFar[endValuePosition] != '/':
                    endValuePosition += 1
                currentChunkRange = tuple([int(x) for x in headerSoFar[startValuePosition : endValuePosition].split('-')])

                state = 1
                headerSoFar = bytearray(b'')
                messageSoFar = bytearray(b'')

            else:

                receivedMessage = bytearray()
                currentlyParsing = False
                continue

        if state == 1:

            i = 0
            while len(messageSoFar) < messageSize and i < len(receivedMessage):
                messageSoFar += receivedMessage[i : i + 1]
                i += 1

            receivedMessage = receivedMessage[i:]

            if len(messageSoFar) == messageSize:

                d[currentChunkRange] = messageSoFar
                chunkSet.pop(currentChunkRange)
                currentChunkRange = None
                messageSoFar = bytearray(b'')
                headerSoFar = bytearray(b'')
                state = 0
                messageSize = int(1e9)
                completeChunks += 1
                received += 1
                #print('Completed chunks:', completeChunks)

            if len(receivedMessage) == 0:
                currentlyParsing = False
                continue

    ans = bytearray(b'')
    for key in sorted(d):
        ans += d[key]

    hashValue = hashlib.md5(bytes(ans)).hexdigest()
    assert hashValue == '70a4b9f4707d258f559f91615297a3ec'

    #print(ans.decode('ASCII'))

'''
variables to be synchronized - chunkSet, completeChunks, d (not necessary since d is an array)
'''

lockSet = threading.Lock()
lockComplete = threading.Lock()

chunkSet = collections.OrderedDict()
totalChunks = 0
completeChunks = 0
fileSize = 6488666
chunkSize = 1024 * 16
d = [None for i in range(0, fileSize, chunkSize)]
timeStamps = [[] for i in range(10000)]

startTime = time.time()

def chunkAllocator(pipelineSize):
    global chunkSet
    localChunkSet = collections.OrderedDict()
    lockSet.acquire()
    for (begin, end) in chunkSet:
        localChunkSet[(begin, end)] = None
        if len(localChunkSet) == pipelineSize:
            break
    for (begin, end) in localChunkSet:
        chunkSet.pop((begin, end))
    lockSet.release()
    return localChunkSet

def downloadSingleThread(threadNumber, serverName, pipelineSize):

    global totalChunks, completeChunks, d, fileSize, chunkSize

    #serverName = 'vayu.iitd.ac.in'
    serverPort = 80
    message = "GET /big.txt HTTP/1.1\r\nHost: " + serverName + "\r\nConnection: keep-alive\r\nRange: bytes="
    messageEnd = "\r\n\r\n"

    fileSize = 6488666
    chunkSize = 1024 * 16 # 16 KB
    while True:
        try:
            clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            clientSocket.settimeout(2)
            clientSocket.connect((serverName, serverPort))
            clientSocket.settimeout(None)
            break
        except:
            continue

    sizeProcessed = 0
    headerSize = 0

    receivedMessage = bytearray(b'')
    currentChunkRange = None # a pair of integers determining the chunk
    messageSoFar = bytearray(b'')
    headerSoFar = bytearray(b'')
    state = 0 # 0 for inside header and 1 for inside message
    messageSize = int(1e9) # total message size - whenever the state is 0, change it to 1e9
    currentlyParsing = False
    totalRightNow = 0

    localChunkSet = collections.OrderedDict()

    while True:
        #print(threadNumber)
        lockComplete.acquire()
        breakCondition = not (completeChunks < totalChunks)
        lockComplete.release()

        if breakCondition:
            return

        while not currentlyParsing:

            try:

                lockComplete.acquire()
                breakCondition = not (completeChunks < totalChunks)
                lockComplete.release()
                if breakCondition:
                    return

                if len(localChunkSet) == 0:
                    localChunkSet = chunkAllocator(pipelineSize)
                    length = len(localChunkSet)
                    if len(localChunkSet) == 0:
                        return
                    for (begin, end) in localChunkSet:
                        sendMessage = message + str(begin) + '-' + str(end) + messageEnd
                        clientSocket.send((sendMessage).encode('ASCII'))

                receivedMessage = bytearray(clientSocket.recv(1024))
                if receivedMessage == bytearray(b''):
                    raise RuntimeError('Broken connection')
                currentlyParsing = True

            except:

                try:

                    currentChunkRange = None
                    messageSoFar = bytearray(b'')
                    headerSoFar = bytearray(b'')
                    state = 0
                    messageSize = int(1e9)

                    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    clientSocket.settimeout(2)
                    clientSocket.connect((serverName, serverPort))
                    clientSocket.settimeout(None)

                    for (begin, end) in localChunkSet:
                        sendMessage = message + str(begin) + '-' + str(end) + messageEnd
                        clientSocket.send((sendMessage).encode('ASCII'))

                    continue

                except:

                    continue

        # now we are currently parsing
        if state == 0:

            assert len(receivedMessage) != 0
            headerSoFar += receivedMessage
            pos = headerSoFar.find(b'\r\n\r\n')

            if pos != -1:

                receivedMessage = headerSoFar[pos + 4:]
                headerSoFar = headerSoFar[:pos + 4].decode('ASCII')
                lengthKeyPosition = headerSoFar.find('Content-Length: ')
                assert lengthKeyPosition != -1
                startValuePosition = lengthKeyPosition + len('Content-Length: ')
                endValuePosition = startValuePosition
                while headerSoFar[endValuePosition] != '\r':
                    endValuePosition += 1
                messageSize = int(headerSoFar[startValuePosition : endValuePosition])
                rangeKeyPosition = headerSoFar.find('Content-Range: bytes ')
                assert rangeKeyPosition != -1
                startValuePosition = rangeKeyPosition + len('Content-Range: bytes ')
                endValuePosition = startValuePosition
                while headerSoFar[endValuePosition] != '/':
                    endValuePosition += 1
                currentChunkRange = tuple([int(x) for x in headerSoFar[startValuePosition : endValuePosition].split('-')])

                state = 1
                headerSoFar = bytearray(b'')
                messageSoFar = bytearray(b'')

                headerSize = pos + 4

            else:

                receivedMessage = bytearray()
                currentlyParsing = False
                continue

        if state == 1:

            i = 0
            while len(messageSoFar) < messageSize and i < len(receivedMessage):
                messageSoFar += receivedMessage[i : i + 1]
                i += 1

            receivedMessage = receivedMessage[i:]

            if len(messageSoFar) == messageSize:

                d[currentChunkRange[0] // chunkSize] = messageSoFar
                localChunkSet.pop(currentChunkRange)

                sizeProcessed += messageSize + headerSize
                timeStamps[threadNumber].append((time.time() - startTime, sizeProcessed))

                currentChunkRange = None
                messageSoFar = bytearray(b'')
                headerSoFar = bytearray(b'')
                state = 0
                messageSize = int(1e9)
                lockComplete.acquire()
                completeChunks += 1
                #print('Completed chunks, Thread number:', completeChunks, threadNumber)
                lockComplete.release()

            if len(receivedMessage) == 0:
                currentlyParsing = False
                continue

    return

def downloadMultipleConnections(l):

    global totalChunks, completeChunks, d, fileSize, chunkSize

    for currentPtr in range(0, fileSize, chunkSize):
        chunkSet[(currentPtr, min(currentPtr + chunkSize, fileSize) - 1)] = None
        totalChunks += 1

    pipelineSize = 1
    #threads = 7
    t = []
    threadCount = 0
    for (url, numThreads) in l:
        t += [threading.Thread(target=downloadSingleThread, args=(threadCount + i, url, pipelineSize,)) for i in range(numThreads)]
        threadCount += numThreads

    for th in t:
        th.start()
    for th in t:
        th.join()

    #print('completed')

    ans = bytearray(b'')
    for k in d:
        ans += k

    hashValue = hashlib.md5(bytes(ans)).hexdigest()
    assert hashValue == '70a4b9f4707d258f559f91615297a3ec'

    #return ans

    #print(ans.decode('ASCII'))

def main():
    #downloadAtOnce()
    #downloadChunkWise()
    #downloadPipelined()

    #l = [('vayu.iitd.ac.in', 10)]
    #l = [('norvig.com', 10)]

    assert len(sys.argv) > 1
    with open(sys.argv[1], newline='') as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        l = [(line[0], int(line[1])) for line in list(reader)]
        #print(l)
        downloadMultipleConnections(l)
        plotData = [list(zip(*timeStamps[i])) for i in range(sum([line[1] for line in l]))]
        #print(plotData)
        for i in range(l[0][1]):
            plt.plot(plotData[i][0], plotData[i][1], color='red')
        if len(l) > 1:
            for i in range(l[0][1], l[0][1] + l[1][1]):
                plt.plot(plotData[i][0], plotData[i][1], color='blue')
        if len(sys.argv) > 2:
            plt.savefig(sys.argv[2])
        else:
            plt.show()

if __name__ == '__main__':
    main()
