import pika, uuid, json

RMQ_HOST = 'ag2478-dev.local'
## cant do hardcoded IP with inconsistent DHCP
## tell group to install avahi and change hostnames

class Controller:
    def __init__(self):
        self.conn = pika.BlockingConnection(pika.ConnectionParameters(RMQ_HOST, 5672, '/', pika.PlainCredentials('repo_user', 'repo_pass')))
        self.ch = self.conn.channel()
        self.ch.exchange_declare('rmq_control', 'direct')
        self.q = self.ch.queue_declare('', exclusive=True).method.queue
        self.ch.basic_consume(self.q, self.on_resp, auto_ack=True)
        self.resp = None
        self.corr_id = None

    def on_resp(self, ch, method, props, body):
        if self.corr_id == props.correlation_id: self.resp = body.decode()

    def send(self, target, action, service):
        self.resp, self.corr_id = None, str(uuid.uuid4())
        payload = json.dumps({"action": action, "service": service})
        self.ch.basic_publish('rmq_control', target, pika.BasicProperties(reply_to=self.q, correlation_id=self.corr_id), payload)
        while self.resp is None: self.conn.process_data_events(time_limit=None)
        return self.resp

if __name__ == "__main__":
    c = Controller()
    while True:
        target = input("\nTarget Hostname (e.g., ag2478-test) or 'q': ").strip()
        if target.lower() == 'q': break

        service = input("Service (nginx/mariadb/rabbitmq-server): ").strip()
        action = input("Action (start/stop/restart/status): ").strip()

        if target and action and service:
            print(f"\n[Output from {target}]:\n{c.send(target, action, service)}")