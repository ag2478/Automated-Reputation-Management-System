"""
import pika, subprocess, json, socket

RMQ_HOST = 'ag2478-dev.local'
## putting myself as the rmq cotroller (EDIT THIS) 
LOCAL_NODE = socket.gethostname()

def on_request(ch, method, props, body):
    data = json.loads(body.decode())
    action = data.get("action")
    service = data.get("service")

    valid_actions = ["start", "stop", "restart", "status"]
    valid_services = ["nginx", "mariadb", "rabbitmq-server"]

    if action in valid_actions and service in valid_services:
        res = subprocess.run(["systemctl", action, service], capture_output=True, text=True)
        out = res.stdout.strip() or res.stderr.strip() or f"✅ {action} executed on {service}."
    else:
        out = "Invalid action or service requested."

# Return the terminal output to the controller
    ch.basic_publish(
        exchange='', 
        routing_key=props.reply_to, 
        properties=pika.BasicProperties(correlation_id=props.correlation_id), 
        body=out
    )    
    ch.basic_ack(method.delivery_tag)

conn = pika.BlockingConnection(pika.ConnectionParameters(RMQ_HOST, 5672, '/', pika.PlainCredentials('repo_user', 'repo_pass')))
ch = conn.channel()
ch.exchange_declare('rmq_control', 'direct')
q = ch.queue_declare('', exclusive=True).method.queue
ch.queue_bind('rmq_control', q, LOCAL_NODE)
ch.basic_consume(q, on_request)
ch.start_consuming()
"""
# i don tknow where i messed up, trying another version of this

import pika, subprocess, json, socket

RMQ_HOST = 'ag2478-dev.local' 
LOCAL_NODE = socket.gethostname()

def on_request(ch, method, props, body):
    try:
        data = json.loads(body.decode())
        action, service = data.get("action"), data.get("service")

        if action in ["start", "stop", "restart", "status"] and service in ["nginx", "mariadb", "rabbitmq-server"]:
            # --no-pager prevents status commands from freezing
            # PIPE ensures compatibility with all Python 3 versions
            res = subprocess.run(
                ["systemctl", "--no-pager", action, service], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            out = res.stdout.decode().strip() or res.stderr.decode().strip() or f"✅ {action} executed on {service}."
        else:
            out = "Invalid action or service requested."
    except Exception as e:
        # If anything fails, send the error back to the controller instead of crashing
        out = f"❌ Agent Error: {str(e)}"

    ch.basic_publish(
        exchange='', 
        routing_key=props.reply_to, 
        properties=pika.BasicProperties(correlation_id=props.correlation_id), 
        body=out.encode('utf-8')
    )
    ch.basic_ack(method.delivery_tag)

conn = pika.BlockingConnection(pika.ConnectionParameters(RMQ_HOST, 5672, '/', pika.PlainCredentials('repo_user', 'repo_pass')))
ch = conn.channel()
ch.exchange_declare('rmq_control', 'direct')
q = ch.queue_declare('', exclusive=True).method.queue
ch.queue_bind('rmq_control', q, LOCAL_NODE)
ch.basic_consume(q, on_request)
ch.start_consuming()