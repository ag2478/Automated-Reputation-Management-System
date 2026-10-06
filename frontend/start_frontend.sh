#!/bin/bash
# Starts the ARMS front end: nginx serves our site on port 7812

cd "$(dirname "$0")"
sudo systemctl restart nginx

if curl -s http://localhost:7812 | grep -q "Hello World!!!"; then
    echo "Front end is running on port 7812"
    python3 send_log.py frontend "front end started on port 7812"
else
    echo "Front end failed to start"
    python3 send_log.py frontend "ERROR: front end failed to start"
fi
