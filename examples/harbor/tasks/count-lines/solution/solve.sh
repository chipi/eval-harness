#!/bin/bash
printf "one\ntwo\nthree\n" > /app/data.txt
wc -l < /app/data.txt > /app/count.txt
