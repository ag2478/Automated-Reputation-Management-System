import pika
import uuid
import time
import sys

CLUSTER_HOSTS = [
    'ag2478-dev',
    'ag2478-test',
    'ag2478-prod',
    'aks55-dev',
    'ojo-dev',
    'jxo-dev'
]

class RpcClient:
    def __init__(self, target_queue):
        self.credentials = pika.PlainCredentials('repo_user', 'repo_pass')
        self.connection = None

        for host in CLUSTER_HOSTS:
            try:
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=host,
                        port=5672,
                        credentials=self.credentials,
                        socket_timeout=4
                    )
                )
                print(f" [✔] Routing RPC via active broker hostname '{host}'")
                break
            except Exception:
                continue

        if not self.connection:
            raise RuntimeError(f"No active RabbitMQ broker reachable across hostnames: {', '.join(CLUSTER_HOSTS)}")

        self.channel = self.connection.channel()
        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue
        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True
        )
        self.response = None
        self.corr_id = None
        self.target_queue = target_queue

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = body

    def call(self, action, service, timeout=15.0):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(
            exchange='',
            routing_key=self.target_queue,
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=f"{action}:{service}"
        )
        start_time = time.time()
        while self.response is None:
            self.connection.process_data_events(time_limit=0.5)
            if time.time() - start_time > timeout:
                return None
        return self.response

def main():
    print("=== Tailscale RabbitMQ Infrastructure Manager (Hostname Mode) ===")
    print(f"Known Hosts: {', '.join(CLUSTER_HOSTS)}")

    # Support CLI args (python3 rmq_controller.py <host> <service> <action>) or interactive input
    if len(sys.argv) == 4:
        target_host = sys.argv[1].strip()
        svc_input = sys.argv[2].strip().lower()
        act_input = sys.argv[3].strip().lower()
    else:
        target_host = input("Enter target hostname: ").strip()
        if not target_host:
            print(" [!] Hostname cannot be empty.")
            return

        svc_input = input("Select service (1: mariadb, 2: rabbitmq, 3: nginx): ").strip().lower()
        act_input = input("Select action (1: start, 2: stop, 3: restart): ").strip().lower()

    svc_map = {
        '1': 'mariadb', '2': 'rabbitmq-server', '3': 'nginx',
        'mariadb': 'mariadb', 'rabbitmq': 'rabbitmq-server',
        'rabbitmq-server': 'rabbitmq-server', 'nginx': 'nginx'
    }
    act_map = {
        '1': 'start', '2': 'stop', '3': 'restart',
        'start': 'start', 'stop': 'stop', 'restart': 'restart'
    }

    service = svc_map.get(svc_input)
    action = act_map.get(act_input)

    if not service or not action:
        print(" [!] Invalid service or action selection.")
        return

    print(f"Sending '{action}' for '{service}' to hostname '{target_host}'...")
    try:
        client = RpcClient(f"agent_{target_host}")
        response = client.call(action, service)
        if response:
            print(f"\n [✔] Response from {target_host}:\n{response.decode()}")
        else:
            print(f" [!] RPC timed out waiting for {target_host}.")
    except Exception as e:
        print(f" [!] Error: {e}")

if __name__ == '__main__':
    main()