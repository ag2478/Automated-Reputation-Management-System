import pika
import sys
import os

def main():
    # 1. Set up the network credentials for RabbitMQ on the Windows Host
    credentials = pika.PlainCredentials('repo_user', 'repo_pass')

    # 2. Configure connection parameters (Pointing to the Windows machine)
    parameters = pika.ConnectionParameters(host='192.168.56.1', 
                                           port=5672, 
                                           virtual_host='/', 
                                           credentials=credentials)

    # 3. Establish the authenticated connection
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    # 4. Declare the same queue as DURABLE
    channel.queue_declare(queue='arms_test_queue', durable=True)

    # 5. Define the Callback function
    def callback(ch, method, properties, body):
        print(f" [x] Read message from queue: {body.decode()}")

    # 6. Tell RabbitMQ to use our callback
    channel.basic_consume(queue='arms_test_queue', 
                          on_message_callback=callback, 
                          auto_ack=True)

    print(' [*] Waiting for messages. To exit press CTRL+C')
    
    # 7. Start listening
    channel.start_consuming()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted, shutting down...')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
