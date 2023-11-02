import pika
import functools
import os
from retry import retry

class AmqpConnection:
    def __init__(self, hostname='localhost', port=5672, username='guest', password='guest', 
                 vhost='/edge-vhost', exchange='cv-exchange', queue='inferencing_stream'):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.connection = None
        self.channel = None
        self.vhost = vhost
        self.exchange = exchange
        self.queue = queue

    def connect(self, connection_name='blackjack-backend'):
        print('Attempting to connect to', self.hostname)
        params = pika.ConnectionParameters(
            host=self.hostname,
            port=self.port,
            virtual_host=self.vhost,
            credentials=pika.PlainCredentials(self.username, self.password),
            client_properties={'connection_name': connection_name})
        self.connection = pika.BlockingConnection(parameters=params)
        self.channel = self.connection.channel()
        print('Connected Successfully to', self.hostname)

    def setup_queues(self):

        self.channel.queue_declare(
            queue='inferencing_stream',
                durable=True,
                arguments={"x-queue-type": "stream", "x-max-age": "1m"}
            )
        if len(self.exchange) > 0:
            self.channel.queue_bind('inferencing_stream', exchange=self.exchange)

    def do_async(self, callback, *args, **kwargs):
        if self.connection.is_open:
            self.connection.add_callback_threadsafe(functools.partial(callback, *args, **kwargs))
        else:
            print('connection to rabbitmq not open')

    def publish(self, payload, routing_key=''):
        if self.connection.is_open and self.channel.is_open:
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.queue,
                body=payload
            )
        else:
            print('connection not open')

    @retry(pika.exceptions.AMQPConnectionError, delay=1, backoff=2)
    def consume(self, on_message):
        if self.connection.is_closed or self.channel.is_closed:
            self.connect()
            self.setup_queues()
        try:
            self.channel.basic_consume(queue='inferencing_stream', auto_ack=True, on_message_callback=on_message)
            self.channel.start_consuming()
        except KeyboardInterrupt:
            print('Keyboard interrupt received')
            self.channel.stop_consuming()
            self.connection.close()
            os._exit(1)
        except pika.exceptions.ChannelClosedByBroker:
            print('Channel Closed By Broker Exception')