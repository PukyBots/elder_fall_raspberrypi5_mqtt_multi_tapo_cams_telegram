#!/bin/bash

sleep 15

export DISPLAY=:0
export XAUTHORITY=/home/tce/.Xauthority
export XDG_RUNTIME_DIR=/run/user/1000

# Play startup sound
cvlc --play-and-exit /home/tce/fall_elder_detector/connect.mp3

cd /home/tce/fall_elder_detector

exec /home/tce/fall_elder_detector/venv/bin/python3 fall_detection.py