import pika
import os
import json
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv()

# Connect to RabbitMQ
credentials = pika.PlainCredentials(os.getenv("RMQ_USER"), os.getenv("RMQ_PASS"))
connection = pika.BlockingConnection(
    pika.ConnectionParameters(host=os.getenv("RMQ_HOST"), port=5672, credentials=credentials)
)
channel = connection.channel()

# The payload now includes a password for bcrypt to verify
payload = {
    "username": "admin", 
    "password": "testpassword123"
}

# Send the request to the queue
channel.basic_publish(
    exchange='',
    routing_key='login_queue',
    properties=pika.BasicProperties(
        reply_to='amq.rabbitmq.reply-to', 
        correlation_id='test-123'
    ),
    body=json.dumps(payload)
)
print(" [x] Secure login request sent to RabbitMQ!")
connection.close()~
