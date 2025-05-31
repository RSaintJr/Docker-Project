import pika
import json
import os
from typing import Optional, Dict, Any

class RabbitMQClient:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

    def connect(self):
        try:
            params = pika.URLParameters(self.rabbitmq_url)
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            print("✅ Conectado ao RabbitMQ")
        except Exception as e:
            print(f"❌ Erro ao conectar com RabbitMQ: {e}")
            self.connection = None
            self.channel = None

    def ensure_connection(self):
        if not self.connection or self.connection.is_closed:
            self.connect()

    def declare_queue(self, queue_name: str, durable: bool = True):
        try:
            self.ensure_connection()
            if self.channel:
                self.channel.queue_declare(queue=queue_name, durable=durable)
        except Exception as e:
            print(f"❌ Erro ao declarar fila {queue_name}: {e}")

    def send_message(self, queue_name: str, message: Dict[Any, Any]) -> bool:
        try:
            self.ensure_connection()
            if not self.channel:
                print("❌ Sem canal RabbitMQ disponível para enviar mensagem.")
                return False
            self.declare_queue(queue_name)
            message_body = json.dumps(message, default=str)
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=message_body,
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"✅ Mensagem enviada para {queue_name}: {message}")
            return True
        except Exception as e:
            print(f"❌ Erro ao enviar mensagem: {e}")
            return False

    def receive_message(self, queue_name: str) -> Optional[Dict]:
        try:
            self.ensure_connection()
            if not self.channel:
                print("❌ Sem canal RabbitMQ disponível para receber mensagem.")
                return None
            self.declare_queue(queue_name)
            method_frame, header_frame, body = self.channel.basic_get(queue=queue_name, auto_ack=True)
            if method_frame:
                message = json.loads(body.decode('utf-8'))
                print(f"✅ Mensagem recebida de {queue_name}: {message}")
                return message
            return None
        except Exception as e:
            print(f"❌ Erro ao receber mensagem: {e}")
            return None

    def close_connection(self):
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                print("✅ Conexão com RabbitMQ fechada")
        except Exception as e:
            print(f"❌ Erro ao fechar conexão: {e}")
