#!/bin/bash

# help message
if [ $# -eq 0 ]
then
    echo $0: usage: replicate_traceroute.sh \<space separated host list\> \
        \[-t \<ttl\> \(default=30\)\] \[-c \<number of packets\> \(default=1\)\] \
        \[-s \<packet size\(bytes\)\> \(default=60\)\]
    exit 1
fi

# default values
ttl=30
count=1
size=60
hosts=()

# parsing input options
while [ $# -gt 0 ]
do
    option=$1
    shift
    case $option in
        -t)
            ttl=$1
            shift;;
        -c)
            count=$1
            shift;;
        -s)
            size=$1
            shift;;
        *)
            hosts+=( "$option" );;
    esac
done

# main body
for host in "${hosts[@]}"
do
    echo Current host: $host
    for (( i=1; i<=$ttl; i++ ))
    do
        out=$(ping -4 -t $i -c $count -s $size $host | grep -o '[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*')
        ctr=0
        for ip in $out
        do
            let "ctr = $ctr + 1"
            if [[ $ctr -eq 2 ]]
            then
                echo Hop number $i
                ping_output=$(ping -4 -t $ttl -c $count -s $size $ip | grep '[fF]rom')
                if [[ -z $ping_output ]]
                then
                    echo No ping response
                else
                    echo $ping_output
                fi
            fi
        done
        if [[ $ctr -lt 2 ]]
        then
            echo Hop number $i
            echo Timeout
        fi
    done
done
