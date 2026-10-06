# Starts, stops or checks all 4 ARMS services at once, over RabbitMQ (no SSH).
# It talks to Andres's rmq_agent.py, which runs on every VM.
# Usage: python3 compose.py start      (or stop / restart / status)

import json
import sys
import uuid
import pika

BROKER_HOST = "ag2478-dev.local"

# VM hostname -> services on that VM (run "hostname" on each VM to check)
VMS = {
    "ag2478-dev": ["rabbitmq-server"],
    "aks55-dev": ["nginx"],
    "jxo-dev": ["mariadb"],
    "ojo-dev": ["arms-backend"],
}

action = sys.argv[1] if len(sys.argv) > 1 else "status"

credentials = pika.PlainCredentials("repo_user", "repo_pass")
connection = pika.BlockingConnection(pika.ConnectionParameters(BROKER_HOST, credentials=credentials))
channel = connection.channel()

reply_queue = channel.queue_declare(queue="", exclusive=True).method.queue
answers = {}
channel.basic_consume(queue=reply_queue, auto_ack=True,
                      on_message_callback=lambda ch, m, props, body: answers.update({props.correlation_id: body.decode()}))

for vm, services in VMS.items():
    for service in services:
        request_id = str(uuid.uuid4())
        channel.basic_publish(exchange="", routing_key=vm,
                              body=json.dumps({"action": action, "service": service}),
                              properties=pika.BasicProperties(reply_to=reply_queue, correlation_id=request_id))

        # wait up to 10 seconds for that VM's agent to answer
        for _ in range(20):
            connection.process_data_events(time_limit=0.5)
            if request_id in answers:
                break

        print(f"--- {service} on {vm} ---")
        print(answers.get(request_id, "no answer (is the agent running on that VM?)"))

connection.close()
