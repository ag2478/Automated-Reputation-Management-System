# Reads every message from the "logs" queue and saves it to one central file.
# Usage: python3 log_collector.py   (leave it running)

import os
import pika

HOST = os.environ["RABBIT_HOST"]
USER = os.environ["RABBIT_USER"]
PASS = os.environ["RABBIT_PASS"]
LOG_FILE = "central.log"


def save(channel, method, properties, body):
    line = body.decode()
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


credentials = pika.PlainCredentials(USER, PASS)
connection = pika.BlockingConnection(pika.ConnectionParameters(host=HOST, credentials=credentials))
channel = connection.channel()
channel.queue_declare(queue="logs", durable=True)
channel.basic_consume(queue="logs", on_message_callback=save, auto_ack=True)

print("Waiting for logs...")
channel.start_consuming()
