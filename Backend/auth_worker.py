import pika
import mysql.connector
import os
import json
import bcrypt
from dotenv import load_dotenv

load_dotenv()

db = mysql.connector.connect(
    host=os.getenv("DB_HOST"), 
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    database=os.getenv("DB_NAME")
)

credentials = pika.PlainCredentials(os.getenv("RMQ_USER"), os.getenv("RMQ_PASS"))
connection = pika.BlockingConnection(
    pika.ConnectionParameters(host=os.getenv("RMQ_HOST"), port=5672, credentials=credentials)
)
channel = connection.channel()
channel.queue_declare(queue='login_queue')

def on_request(ch, method, props, body):
    request = json.loads(body)
    username = request.get('username')
    provided_password = request.get('password') 
    
    print(f"[.] Processing login attempt for {username}")

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()

    if user:
        stored_hash = user['password_hash'].encode('utf-8')
        
        if bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash):
            response = {"status": "success", "message": "Login approved"}
            print(f"[+] Login successful for {username}")
        else:
            response = {"status": "fail", "message": "Invalid password"}
            print(f"[-] Invalid password for {username}")
    else:
        response = {"status": "fail", "message": "User not found"}
        print(f"[-] User {username} not found")

    ch.basic_publish(
        exchange='',
        routing_key=props.reply_to,
        properties=pika.BasicProperties(correlation_id=props.correlation_id),
        body=json.dumps(response)
    )
    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_consume(queue='login_queue', on_message_callback=on_request)
print(" [x] Awaiting secure RPC requests on 'login_queue'")
channel.start_consuming()
