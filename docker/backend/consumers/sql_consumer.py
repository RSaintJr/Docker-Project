#!/usr/bin/env python3
import pika
import json
import time
import logging
import signal
import sys
from datetime import datetime
from database.sql_connection import get_session_with_retry, User

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SQLConsumer:
    def __init__(self, rabbitmq_url="amqp://guest:guest@rabbitmq:5672/"):
        self.rabbitmq_url = rabbitmq_url
        self.connection = None
        self.channel = None
        self.queue_name = 'sql_fallback'
        self.max_retries = 10
        self.retry_delay = 5
        self.running = True
        
        # Setup graceful shutdown
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
                
                # Declare queue with durability
                self.channel.queue_declare(
                    queue=self.queue_name, 
                    durable=True,
                    arguments={'x-message-ttl': 86400000}  # 24 hours TTL
                )
                
                # Set QoS to process one message at a time
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
    
    def wait_for_postgres(self):
        """Wait for PostgreSQL to be available"""
        logger.info("🔄 Aguardando PostgreSQL ficar disponível...")
        
        for attempt in range(1, 31):  
            try:
                db = get_session_with_retry(retries=1, delay=1)
                db.execute("SELECT 1")
                db.close()
                logger.info("✅ PostgreSQL está disponível!")
                return True
            except Exception as e:
                logger.info(f"⏳ Aguardando PostgreSQL... tentativa {attempt}/30")
                time.sleep(10)
        
        logger.error("❌ PostgreSQL não ficou disponível em tempo hábil")
        return False
    
    def process_message(self, ch, method, properties, body):
        """Process incoming message"""
        try:
            # Parse message
            data = json.loads(body.decode('utf-8'))
            logger.info(f"📨 Processando mensagem: {data}")
            
            # Validate required fields
            if 'name' not in data or 'email' not in data:
                logger.error(f"❌ Mensagem inválida - campos obrigatórios ausentes: {data}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                return
            
            # Get database session with retry
            db = get_session_with_retry(retries=3, delay=2)
            
            try:
                # Check if user already exists
                existing_user = db.query(User).filter(User.email == data['email']).first()
                
                if existing_user:
                    logger.warning(f"⚠️  Usuário já existe: {data['email']}")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    return
                
                # Create new user
                db_user = User(
                    name=data['name'], 
                    email=data['email']
                )
                db.add(db_user)
                db.commit()
                db.refresh(db_user)
                
                logger.info(f"✅ Usuário reinserido com sucesso: {data['name']} ({data['email']}) - ID: {db_user.id}")
                
                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except Exception as e:
                logger.error(f"❌ Erro ao processar usuário: {e}")
                db.rollback()
                
                # Requeue message for retry (with limit)
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
                
            finally:
                db.close()
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Erro ao decodificar JSON: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao processar mensagem: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def start_consuming(self):
        """Start consuming messages"""
        try:
            # Wait for dependencies
            if not self.wait_for_postgres():
                return False
            
            if not self.connect_rabbitmq():
                return False
            
            # Setup consumer
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=self.process_message
            )
            
            logger.info(f"🟢 SQL Consumer iniciado, aguardando mensagens na fila '{self.queue_name}'...")
            logger.info("🔄 Para parar o consumer, pressione CTRL+C")
            
            # Start consuming
            while self.running:
                try:
                    self.connection.process_data_events(time_limit=1)
                except pika.exceptions.AMQPConnectionError:
                    logger.error("❌ Conexão RabbitMQ perdida, tentando reconectar...")
                    if not self.connect_rabbitmq():
                        break
                    
                    # Re-setup consumer after reconnection
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
    consumer = SQLConsumer()
    
    try:
        success = consumer.start_consuming()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()