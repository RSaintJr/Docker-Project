import pika
import json
import time
import logging
import signal
import sys
from datetime import datetime
from database.nosql_connection import get_mongo_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NoSQLConsumer:
    def __init__(self, rabbitmq_url="amqp://guest:guest@rabbitmq:5672/"):
        self.rabbitmq_url = rabbitmq_url
        self.connection = None
        self.channel = None
        self.queue_name = 'nosql_fallback'
        self.max_retries = 10
        self.retry_delay = 5
        self.running = True
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle graceful shutdown"""
        logger.info("🛑 Recebido sinal de parada, finalizando consumer...")
        self.running = False
        if self.connection and not self.connection.is_closed:
            self.connection.close()
        sys.exit(0)
    
    def connect_rabbitmq(self):
        """Connect to RabbitMQ with retry logic"""
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"🔌 Tentativa {attempt}/{self.max_retries}: Conectando ao RabbitMQ...")
                
                params = pika.URLParameters(self.rabbitmq_url)
                self.connection = pika.BlockingConnection(params)
                self.channel = self.connection.channel()
                
                self.channel.queue_declare(
                    queue=self.queue_name, 
                    durable=True,
                    arguments={'x-message-ttl': 86400000} 
                )
                
                self.channel.basic_qos(prefetch_count=1)
                
                logger.info("✅ Conectado ao RabbitMQ com sucesso!")
                return True
                
            except Exception as e:
                logger.error(f"❌ Erro na conexão RabbitMQ (tentativa {attempt}): {e}")
                if attempt < self.max_retries:
                    logger.info(f"⏳ Aguardando {self.retry_delay}s antes da próxima tentativa...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("❌ Falha ao conectar ao RabbitMQ após todas as tentativas")
                    return False
        
        return False
    
    def wait_for_mongodb(self):
        """Wait for MongoDB to be available"""
        logger.info("🔄 Aguardando MongoDB ficar disponível...")
        
        for attempt in range(1, 31):  
            try:
                client = get_mongo_client()
                client.admin.command("ping")
                logger.info("✅ MongoDB está disponível!")
                return True
            except Exception as e:
                logger.info(f"⏳ Aguardando MongoDB... tentativa {attempt}/30")
                time.sleep(10)
        
        logger.error("❌ MongoDB não ficou disponível em tempo hábil")
        return False
    
    def process_message(self, ch, method, properties, body):
        """Process incoming message"""
        try:
            data = json.loads(body.decode('utf-8'))
            logger.info(f"📨 Processando mensagem: {data}")
            
            if 'action' not in data:
                logger.error(f"❌ Mensagem inválida - campo 'action' ausente: {data}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                return
            
            client = get_mongo_client()
            db = client.sistema_nosql
            collection = db.logs
            
            log_entry = {
                "action": data.get('action'),
                "details": data.get('details', {}),
                "timestamp": datetime.now(),
                "source": "fallback_queue",
                "processed_at": datetime.now().isoformat()
            }
            
            if 'timestamp' in data:
                log_entry['original_timestamp'] = data['timestamp']
            
            result = collection.insert_one(log_entry)
            
            logger.info(f"✅ Log reinserido com sucesso: {data.get('action')} - ID: {result.inserted_id}")
            
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Erro ao decodificar JSON: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar log: {e}")
            
            if hasattr(properties, 'headers') and properties.headers:
                retry_count = properties.headers.get('retry_count', 0)
            else:
                retry_count = 0
            
            if retry_count < 3:
                logger.info(f"🔄 Requeuing message (retry {retry_count + 1}/3)")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            else:
                logger.error("❌ Máximo de tentativas excedido, descartando mensagem")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    def start_consuming(self):
        """Start consuming messages"""
        try:
            if not self.wait_for_mongodb():
                return False
            
            if not self.connect_rabbitmq():
                return False
            
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=self.process_message
            )
            
            logger.info(f"🟢 NoSQL Consumer iniciado, aguardando mensagens na fila '{self.queue_name}'...")
            logger.info("🔄 Para parar o consumer, pressione CTRL+C")
            
            while self.running:
                try:
                    self.connection.process_data_events(time_limit=1)
                except pika.exceptions.AMQPConnectionError:
                    logger.error("❌ Conexão RabbitMQ perdida, tentando reconectar...")
                    if not self.connect_rabbitmq():
                        break
                    
                    self.channel.basic_consume(
                        queue=self.queue_name,
                        on_message_callback=self.process_message
                    )
                    
        except KeyboardInterrupt:
            logger.info("🛑 Consumer interrompido pelo usuário")
        except Exception as e:
            logger.error(f"❌ Erro fatal no consumer: {e}")
            return False
        finally:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                logger.info("🔌 Conexão RabbitMQ fechada")
        
        return True

def main():
    """Main function"""
    consumer = NoSQLConsumer()
    
    try:
        success = consumer.start_consuming()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()