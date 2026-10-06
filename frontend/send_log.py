# Sends one log message to the "logs" queue in RabbitMQ.
# Usage: python3 send_log.py frontend "front end started"

import os
import sys
import socket
from datetime import datetime
import pika

HOST = os.environ["RABBIT_HOST"]
USER = os.environ["RABBIT_USER"]
PASS = os.environ["RABBIT_PASS"]

service = sys.argv[1]
message = sys.argv[2]

time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
line = f"{time} {socket.gethostname()} {service}: {message}"

credentials = pika.PlainCredentials(USER, PASS)
connection = pika.BlockingConnection(pika.ConnectionParameters(host=HOST, credentials=credentials))
channel = connection.channel()
channel.queue_declare(queue="logs", durable=True)
channel.basic_publish(exchange="", routing_key="logs", body=line)
connection.close()

print("Sent log:", line)
