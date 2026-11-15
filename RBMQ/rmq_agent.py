import pika
import subprocess
import socket
import time

CLUSTER_HOSTS = [
    'ag2478-dev',
    'ag2478-test',
    'ag2478-prod',
    'aks55-dev',
    'ojo-dev',
    'jxo-dev'
]

def get_connection():
    credentials = pika.PlainCredentials('repo_user', 'repo_pass')
    local_host = socket.gethostname()

    # Try the local hostname first, then fail over to peer hostnames
    ordered_hosts = [local_host] + [h for h in CLUSTER_HOSTS if h != local_host]

    for host in ordered_hosts:
        try:
            params = pika.ConnectionParameters(
                host=host,
                port=5672,
                credentials=credentials,
                socket_timeout=3,
                heartbeat=15
            )
            conn = pika.BlockingConnection(params)
            print(f" [✔] Connected to RabbitMQ broker at hostname '{host}'")
            return conn
        except Exception:
            continue
    raise RuntimeError("All RabbitMQ cluster hostnames are unreachable.")

def on_request(ch, method, props, body):
    try:
        request_message = body.decode()
        action, service = request_message.split(':', 1)
        print(f" [x] Received: Action='{action}', Service='{service}'")

        # Force boot if starting or restarting rabbitmq-server during a majority outage
        if service == 'rabbitmq-server' and action in ['start', 'restart']:
            subprocess.run(['sudo', 'rabbitmqctl', 'force_boot'], capture_output=True, text=True)

        cmd = ['sudo', 'systemctl', action, service]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            response = f"SUCCESS: {action} {service} on {socket.gethostname()}.\n{result.stdout}"
        else:
            response = f"FAILED ({result.returncode}): {result.stderr}"
    except Exception as e:
        response = f"ERROR: {str(e)}"

    ch.basic_publish(
        exchange='',
        routing_key=props.reply_to,
        properties=pika.BasicProperties(correlation_id=props.correlation_id),
        body=response
    )
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    hostname = socket.gethostname()
    queue_name = f"agent_{hostname}"

    while True:
        try:
            connection = get_connection()
            channel = connection.channel()
            channel.queue_declare(queue=queue_name)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=on_request)
            print(f" [x] Agent active on '{hostname}', listening on '{queue_name}'...")
            channel.start_consuming()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f" [!] Broker connection lost ({e}). Failing over to next available hostname in 3s...")
            time.sleep(3)

if __name__ == '__main__':
    main()