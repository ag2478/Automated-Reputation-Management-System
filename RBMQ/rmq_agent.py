import pika, subprocess, socket, json

BROKER_HOST = 'ag2478-dev.local' 
MY_QUEUE = socket.gethostname()     
#ned to add other services cause REASONS
def on_request(ch, method, props, body):
    try:
        # I do not understand JSON
        data = json.loads(body.decode('utf-8'))
        action = data.get("action")
        service = data.get("service")
        
        # error check commands cause i cant spell
        valid_actions = ["start", "stop", "restart", "status"]
        valid_services = ["nginx", "mariadb", "rabbitmq-server"]
        
        if action in valid_actions and service in valid_services:
            output = subprocess.getoutput(f"systemctl --no-pager {action} {service}")
            if not output: output = f"{action} command sent to {service}."
        else:
            output = "Invalid command or service requested."
    except Exception as e:
        output = f"Agent Error: {str(e)}"
        
    ch.basic_publish(
        exchange='', 
        routing_key=props.reply_to,
        properties=pika.BasicProperties(correlation_id=props.correlation_id),
        body=output.encode('utf-8')
    )
    ch.basic_ack(delivery_tag=method.delivery_tag)
# login needed for controller
creds = pika.PlainCredentials('repo_user', 'repo_pass')
conn = pika.BlockingConnection(pika.ConnectionParameters(BROKER_HOST, credentials=creds))
ch = conn.channel()

ch.queue_declare(queue=MY_QUEUE)
ch.basic_consume(queue=MY_QUEUE, on_message_callback=on_request)
ch.start_consuming()