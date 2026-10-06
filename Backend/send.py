import pika

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

# 4. Declare the queue as DURABLE (Fixes the deprecation error)
channel.queue_declare(queue='arms_test_queue', durable=True)

# 5. Write/Publish the message to the queue
message = 'Hello from the ARMS Backend!'
channel.basic_publish(exchange='', 
                      routing_key='arms_test_queue', 
                      body=message,
                      properties=pika.BasicProperties(
                         delivery_mode=pika.DeliveryMode.Persistent
                      ))

print(f" [x] Successfully wrote '{message}' to the queue.")

# 6. Close the connection
connection.close()
