import pika, subprocess

# --- CONFIGURATION ---
REPO_PATH = '/home/dev/Automated-Reputation-Management-System'
RMQ_HOST = '192.168.56.1' #CHECK VM INSTALL IP
RMQ_USER = 'repo_user' #FROM RBMQ INSTALL
RMQ_PASS = 'repo_pass'
# ---------------------

def callback(ch, method, properties, body):
    command = body.decode()
    if command == "pull":
        print("Received 'pull' command. Executing git pull...")
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=REPO_PATH)
        result = subprocess.run(["git", "pull"], cwd=REPO_PATH, capture_output=Tr>
        print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)

print(f"Connecting to RabbitMQ at {RMQ_HOST}...")
credentials = pika.PlainCredentials(RMQ_USER, RMQ_PASS)
connection = pika.BlockingConnection(pika.ConnectionParameters(RMQ_HOST, 5672, '/>
channel = connection.channel()

channel.exchange_declare(exchange='git_updates', exchange_type='fanout')

result = channel.queue_declare(queue='', exclusive=True)
queue_name = result.method.queue
channel.queue_bind(exchange='git_updates', queue=queue_name)

print('Connected! Waiting for git commands...')
channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=Tr>
channel.start_consuming()
ag2478/Automated-Reputation-Management-System ##CHANGE TO YOUR GIT