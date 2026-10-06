import pika, uuid, json

# going to be ag2478-dev or my laptop
# DNS solves random ip on network
BROKER_HOST = 'ag2478-dev.local' 

class RPC:
    def __init__(self):
        creds = pika.PlainCredentials('repo_user', 'repo_pass')
        self.conn = pika.BlockingConnection(pika.ConnectionParameters(BROKER_HOST, credentials=creds))
        self.ch = self.conn.channel()
        self.reply_q = self.ch.queue_declare(queue='', exclusive=True).method.queue
        self.ch.basic_consume(queue=self.reply_q, on_message_callback=self.on_reply, auto_ack=True)
        self.resp = None    
        #ALL OF THIS ^^^^ for it to undersand why im asking?!?!?!

    def on_reply(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.resp = body.decode('utf-8')

    def call(self, target_queue, action, service):
        self.resp, self.corr_id = None, str(uuid.uuid4())
        
        # I STILL DONT UNDERSTAND JSON
        payload = json.dumps({"action": action, "service": service})
        
        self.ch.basic_publish(
            exchange='', 
            routing_key=target_queue,
            properties=pika.BasicProperties(reply_to=self.reply_q, correlation_id=self.corr_id),
            body=payload
        )
        while self.resp is None: 
            self.conn.process_data_events(time_limit=None)
        return self.resp

if __name__ == '__main__':
    rpc = RPC()
    
    service_menu = {"1": "nginx", "2": "rabbitmq-server", "3": "mariadb"}
    action_menu = {"1": "status", "2": "restart", "3": "stop", "4": "start"}

    # got to simplify this, i aint typing that shizz out agian
    while True:
        print("\n" + "="*40)
        target = input("Enter target VM DNS/Hostname (or 'q' to quit): ").strip()
        if target.lower() == 'q': break
        if not target: continue

        # I AM SICK OF TYPING
        print("\nSelect Service:")
        print("  1) Nginx")
        print("  2) RabbitMQ")
        print("  3) MariaDB")
        s_choice = input("Choice (1-3): ").strip()
        
        if s_choice not in service_menu:
            print("Invalid service choice.")
            continue
        
        print("\nSelect Action:")
        print("  1) Status\n  2) Restart\n  3) Stop\n  4) Start")
        a_choice = input("Choice (1-4): ").strip()
        
        if a_choice not in action_menu:
            print("Invalid action choice.")
            continue
            
        service = service_menu[s_choice]
        action = action_menu[a_choice]

        #i have never done this much python, why do people do this?!
        print(f"\n--- Output from {target} ({service}) ---")
        print(rpc.call(target, action, service))
        print("-" * 40)