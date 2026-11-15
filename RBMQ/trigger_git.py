import pika
import sys

CLUSTER_HOSTS = [
    'ag2478-dev',
    'ag2478-test',
    'ag2478-prod',
    'aks55-dev',
    'ojo-dev',
    'jxo-dev'
]

def main():
    credentials = pika.PlainCredentials('repo_user', 'repo_pass')
    connection = None
    connected_host = None

    for host in CLUSTER_HOSTS:
        try:
            parameters = pika.ConnectionParameters(
                host=host,
                port=5672,
                virtual_host='/',
                credentials=credentials,
                socket_timeout=4
            )
            connection = pika.BlockingConnection(parameters)
            connected_host = host
            break
        except Exception:
            continue

    if not connection:
        print(" [!] Could not connect to any RabbitMQ broker hostname.", file=sys.stderr)
        sys.exit(1)

    channel = connection.channel()

    exchange_name = 'deployment_exchange'
    channel.exchange_declare(exchange=exchange_name, exchange_type='fanout')

    message = 'GIT_PULL_UPDATE'
    channel.basic_publish(
        exchange=exchange_name,
        routing_key='',
        body=message,
        properties=pika.BasicProperties(
            delivery_mode=pika.DeliveryMode.Persistent
        )
    )

    print(f" [✔] Broadcasted '{message}' to '{exchange_name}' via broker '{connected_host}'")
    connection.close()

if __name__ == '__main__':
    main()
EOF