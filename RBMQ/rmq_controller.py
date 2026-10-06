import pika, subprocess, socket

# UPDATE THIS to the Bridged IP address of ag2478-dev
BROKER_IP = '192.168.x.x' 
MY_QUEUE = socket.gethostname()     

def on_request(ch, method, props, body):
    action = body.decode()
    if action in ["start", "stop", "restart", "status"]:
        output = subprocess.getoutput(f"systemctl --no-pager {action} rabbitmq-server")
        if not output: output = f"{action} command sent successfully."
    else:
        output = "Invalid command."
        
    ch.basic_publish(exchange='', routing_key=props.reply_to,
                     properties=pika.BasicProperties(correlation_id=props.correlation_id),
                     body=output)
    ch.basic_ack(delivery_tag=method.delivery_tag)

creds = pika.PlainCredentials('repo_user', 'repo_pass')
conn = pika.BlockingConnection(pika.ConnectionParameters(BROKER_IP, credentials=creds))
ch = conn.channel()

ch.queue_declare(queue=MY_QUEUE)
ch.basic_consume(queue=MY_QUEUE, on_message_callback=on_request)
ch.start_consuming()