import pika
import json
import bcrypt
import mysql.connector
import uuid

# VM names, not IPs: each VM's /etc/hosts maps jxo-dev and ag2478-dev to their ZeroTier IPs
db = mysql.connector.connect(host="jxo-dev", user="arms_app", password="ARMS2026", database="reputation_app")
cursor = db.cursor()

connection = pika.BlockingConnection(pika.ConnectionParameters('ag2478-dev', credentials=pika.PlainCredentials('repo_user', 'repo_pass')))
channel = connection.channel()
channel.queue_declare(queue='fe_to_be_queue', durable=True)

def on_request(ch, method, props, body):
    data = json.loads(body)
    action = data.get('action')
    response = {'status': 'error', 'message': 'Unknown action'}

    # reconnect if MariaDB was restarted; if it's down, answer instead of crashing
    try:
        db.ping(reconnect=True, attempts=2, delay=1)
        cursor = db.cursor()
    except Exception:
        action = None
        response = {'status': 'error', 'message': 'Database is down'}

    if action == 'register':
        username, email = data['username'], data['email']
        hashed_pw = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
        try:
            cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)", (username, email, hashed_pw.decode('utf-8')))
            db.commit()
            print(f"Registered {username}")
            response = {'status': 'success'}
        except Exception as e:
            response = {'status': 'error', 'message': str(e)}

    elif action == 'login':
        username = data['username']
        try:
            cursor.execute("SELECT password_hash FROM users WHERE username = %s", (username,))
            result = cursor.fetchone()
            if result and bcrypt.checkpw(data['password'].encode('utf-8'), result[0].encode('utf-8')):
                print(f"Logged in {username}")
                response = {'status': 'success', 'sessionId': str(uuid.uuid4())}
            else:
                response = {'status': 'error', 'message': 'Invalid credentials'}
        except Exception as e:
            response = {'status': 'error', 'message': str(e)}

    ch.basic_publish(exchange='', routing_key=props.reply_to, properties=pika.BasicProperties(correlation_id=props.correlation_id), body=json.dumps(response))
    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='fe_to_be_queue', on_message_callback=on_request)
print("Awaiting RPC requests...")
channel.start_consuming()
