# Starts, stops or checks every ARMS service across all VMs, over RabbitMQ (no SSH).
# Talks to Andres's rmq_agent.py, which listens on the queue "agent_<hostname>" on each VM
# and expects a plain "action:service" message (for example "status:nginx").
# Usage: python3 compose.py status      (or start / stop / restart)

import os
import socket
import sys
import time
import uuid
import pika

# Same broker list as rmq_agent.py: try each cluster node until one answers.
CLUSTER_HOSTS = ["ag2478-dev", "ag2478-test", "ag2478-prod", "aks55-dev", "ojo-dev", "jxo-dev"]

# VM hostname -> services on that VM.
# EDIT THIS to match what is actually installed on each VM tonight.
# A service that isn't installed on a VM will show up as FAILED.
VMS = {
    "jxo-dev":   ["mariadb"],                     # database node 1 (Josue)
    "ojo-dev":   ["arms-backend"],                # back end node 1 (Oluwasanmi)
    "aks55-dev": ["nginx", "arms-frontend"],      # front end node 1 (Alexander)
    # Milestone 4 extra nodes: uncomment the ones you set up
    # "aks55-dev": ["mariadb", "nginx", "arms-frontend"],   # if Josue's DB node 2 is on aks55-dev
    # "ojo-dev":   ["mariadb", "arms-backend"],             # if Josue's DB node 3 is on ojo-dev
    # "ag2478-test": ["arms-backend"],                      # back end node 2
    # "ag2478-prod": ["nginx", "arms-frontend"],            # front end node 2
}

# Start the database first and the front end last; stop in the reverse order.
ORDER = ["mariadb", "rabbitmq-server", "arms-backend", "arms-frontend", "nginx"]

action = sys.argv[1] if len(sys.argv) > 1 else "status"
if action not in ("start", "stop", "restart", "status"):
    sys.exit("Usage: python3 compose.py status|start|stop|restart")

user = os.getenv("RABBITMQ_USER", "repo_user")
password = os.getenv("RABBITMQ_PASS", "repo_pass")


def connect():
    for host in CLUSTER_HOSTS:
        try:
            conn = pika.BlockingConnection(pika.ConnectionParameters(
                host=host, credentials=pika.PlainCredentials(user, password),
                socket_timeout=3, blocked_connection_timeout=5))
            return host, conn
        except Exception:
            print(f"  (broker {host} not reachable, trying the next one)")
    sys.exit("No RabbitMQ cluster node is reachable.")


broker, connection = connect()
channel = connection.channel()
reply_queue = channel.queue_declare(queue="", exclusive=True).method.queue
answers = {}
channel.basic_consume(queue=reply_queue, auto_ack=True,
                      on_message_callback=lambda ch, m, props, body: answers.update({props.correlation_id: body.decode()}))

jobs = [(vm, svc) for vm, services in VMS.items() for svc in services]
jobs.sort(key=lambda j: ORDER.index(j[1]) if j[1] in ORDER else len(ORDER))
if action == "stop":
    jobs.reverse()

print(f"ARMS composer: {action.upper()} via RabbitMQ broker {broker} (from {socket.gethostname()})")
print(f"{'VM':<13}{'SERVICE':<17}RESULT")
print("-" * 60)

for vm, service in jobs:
    request_id = str(uuid.uuid4())
    channel.basic_publish(exchange="", routing_key=f"agent_{vm}",
                          body=f"{action}:{service}",
                          properties=pika.BasicProperties(reply_to=reply_queue, correlation_id=request_id))
    deadline = time.time() + 10
    while request_id not in answers and time.time() < deadline:
        connection.process_data_events(time_limit=0.5)

    reply = answers.get(request_id)
    if reply is None:
        result = "NO ANSWER (is rmq-agent running on that VM?)"
    elif action == "status":
        # systemctl status exits 0 when running and 3 when stopped
        result = "active (running)" if reply.startswith("SUCCESS") else "INACTIVE / DOWN"
    else:
        result = "OK" if reply.startswith("SUCCESS") else reply.strip().splitlines()[0][:60]
    print(f"{vm:<13}{service:<17}{result}")

connection.close()
