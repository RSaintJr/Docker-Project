from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import text
import asyncio
import logging
import json

from database.sql_connection import User, create_tables, get_session_with_retry, check_database_health
from database.nosql_connection import get_mongo_client
from messaging.rabbitmq_client import RabbitMQClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sistema de Containers",
    description="API integrada com PostgreSQL, MongoDB e RabbitMQ com fallback automático",
    version="1.0.0"
)

# Modelos Pydantic
class UserCreate(BaseModel):
    name: str
    email: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime

class LogCreate(BaseModel):
    action: str
    details: Dict[str, Any]

class MessageCreate(BaseModel):
    queue_name: str
    message: Dict[str, Any]

class FallbackResponse(BaseModel):
    success: bool
    fallback_used: bool
    message: str
    queue_name: Optional[str] = None

# Instâncias
rabbitmq = RabbitMQClient()

# Configurações das filas de fallback
FALLBACK_QUEUES = {
    "postgres": "postgres_fallback_queue",
    "mongo": "mongo_fallback_queue",
    "users": "users_fallback_queue",
    "logs": "logs_fallback_queue"
}

async def wait_for_services():
    """Aguarda todos os serviços ficarem disponíveis"""
    logger.info("🔄 Aguardando serviços ficarem disponíveis...")
    
    # Aguarda PostgreSQL
    postgres_ready = False
    for attempt in range(1, 31):  # 30 tentativas = ~5 minutos
        try:
            if check_database_health():
                logger.info("✅ PostgreSQL está disponível!")
                postgres_ready = True
                break
        except Exception as e:
            logger.info(f"⏳ Aguardando PostgreSQL... tentativa {attempt}/30")
            await asyncio.sleep(10)
    
    if not postgres_ready:
        logger.error("❌ PostgreSQL não ficou disponível em tempo hábil")
        raise Exception("PostgreSQL timeout")

def setup_fallback_queues():
    """Configura as filas de fallback no RabbitMQ"""
    try:
        for queue_name in FALLBACK_QUEUES.values():
            rabbitmq.declare_queue(queue_name)
        logger.info("✅ Filas de fallback configuradas")
    except Exception as e:
        logger.error(f"❌ Erro ao configurar filas de fallback: {e}")

def send_to_fallback_queue(queue_name: str, data: dict, operation_type: str = "unknown") -> bool:
    """Envia dados para fila de fallback com metadados"""
    try:
        fallback_data = {
            "operation_type": operation_type,
            "timestamp": datetime.now().isoformat(),
            "data": data,
            "retry_count": 0
        }
        
        success = rabbitmq.send_message(queue_name, fallback_data)
        if success:
            logger.info(f"📤 Dados enviados para fila de fallback: {queue_name}")
            return True
        else:
            logger.error(f"❌ Falha ao enviar para fila de fallback: {queue_name}")
            return False
    except Exception as e:
        logger.error(f"❌ Erro ao enviar para fallback: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Inicializando aplicação...")
    
    try:
        # Aguarda serviços ficarem disponíveis
        await wait_for_services()
        
        # Cria tabelas
        logger.info("📋 Criando/verificando tabelas...")
        create_tables()
        
        # Configura filas de fallback
        setup_fallback_queues()
        
        # Inicia worker automático de fallback
        fallback_worker.start()
        
        logger.info("✅ Aplicação inicializada com sucesso!")
        
    except Exception as e:
        logger.error(f"❌ Erro na inicialização: {e}")
        # Não falha a aplicação, mas registra o erro
        pass

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Encerrando aplicação...")
    fallback_worker.stop()
    logger.info("✅ Aplicação encerrada")

@app.get("/")
def root():
    return {"message": "Sistema de Containers rodando!", "status": "OK"}

@app.get("/health")
def health_check():
    status = {
        "api": "OK",
        "postgres": "UNKNOWN",
        "mongo": "UNKNOWN", 
        "rabbitmq": "UNKNOWN",
        "timestamp": datetime.now().isoformat()
    }
    
    # Verificação PostgreSQL
    try:
        if check_database_health():
            status["postgres"] = "OK"
        else:
            status["postgres"] = "ERROR"
    except Exception as e:
        status["postgres"] = f"ERROR: {str(e)}"
    
    # Verificação MongoDB
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        status["mongo"] = "OK"
    except Exception as e:
        status["mongo"] = f"ERROR: {str(e)}"
    
    # Verificação RabbitMQ
    try:
        if rabbitmq.connection and not rabbitmq.connection.is_closed:
            status["rabbitmq"] = "OK"
        else:
            status["rabbitmq"] = "ERROR: Connection closed"
    except Exception as e:
        status["rabbitmq"] = f"ERROR: {str(e)}"
    
    return status

@app.post("/users/", response_model=Dict[str, Any])
async def create_user(user: UserCreate):
    # Primeiro tenta criar no PostgreSQL
    try:
        db = get_session_with_retry(retries=2, delay=1)
        try:
            # Verifica se usuário já existe
            existing_user = db.query(User).filter(User.email == user.email).first()
            if existing_user:
                raise HTTPException(status_code=409, detail="Email já cadastrado")
            
            db_user = User(name=user.name, email=user.email)
            db.add(db_user)
            db.commit()
            db.refresh(db_user)
            
            logger.info(f"✅ Usuário criado no PostgreSQL: {user.email}")
            return {
                "success": True,
                "fallback_used": False,
                "user": {
                    "id": db_user.id,
                    "name": db_user.name,
                    "email": db_user.email,
                    "created_at": db_user.created_at
                },
                "message": "Usuário criado com sucesso no PostgreSQL"
            }
            
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ PostgreSQL indisponível. Erro: {e}")
        
        # Fallback: enviar para RabbitMQ
        fallback_success = send_to_fallback_queue(
            FALLBACK_QUEUES["users"], 
            {"name": user.name, "email": user.email},
            "create_user"
        )
        
        if fallback_success:
            return {
                "success": True,
                "fallback_used": True,
                "message": "PostgreSQL indisponível. Usuário enviado para fila de processamento.",
                "queue_name": FALLBACK_QUEUES["users"]
            }
        else:
            raise HTTPException(
                status_code=503, 
                detail="PostgreSQL indisponível e falha no fallback para RabbitMQ"
            )

@app.get("/users/")
async def get_users():
    try:
        db = get_session_with_retry(retries=2, delay=1)
        try:
            users = db.query(User).all()
            logger.info(f"📋 Listando {len(users)} usuários do PostgreSQL")
            return {
                "success": True,
                "fallback_used": False,
                "users": [
                    {
                        "id": user.id,
                        "name": user.name,
                        "email": user.email,
                        "created_at": user.created_at
                    } for user in users
                ],
                "message": f"{len(users)} usuários encontrados"
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ Erro ao acessar PostgreSQL: {e}")
        
        return {
            "success": False,
            "fallback_used": True,
            "users": [],
            "message": f"PostgreSQL indisponível. Dados podem estar na fila: {FALLBACK_QUEUES['users']}",
            "error": str(e)
        }

@app.post("/logs/")
def create_log(log: LogCreate):
    # Primeiro tenta salvar no MongoDB
    try:
        client = get_mongo_client()
        db = client.sistema_nosql
        collection = db.logs
        log_entry = {
            "action": log.action,
            "details": log.details,
            "timestamp": datetime.now()
        }
        result = collection.insert_one(log_entry)
        logger.info(f"📝 Log criado no MongoDB: {result.inserted_id}")
        return {
            "success": True,
            "fallback_used": False,
            "log_id": str(result.inserted_id),
            "message": "Log salvo com sucesso no MongoDB"
        }
    except Exception as e:
        logger.error(f"❌ MongoDB indisponível. Erro: {e}")
        
        # Fallback: enviar para RabbitMQ
        fallback_success = send_to_fallback_queue(
            FALLBACK_QUEUES["logs"],
            {"action": log.action, "details": log.details},
            "create_log"
        )
        
        if fallback_success:
            return {
                "success": True,
                "fallback_used": True,
                "message": "MongoDB indisponível. Log enviado para fila de processamento.",
                "queue_name": FALLBACK_QUEUES["logs"]
            }
        else:
            raise HTTPException(
                status_code=503,
                detail="MongoDB indisponível e falha no fallback para RabbitMQ"
            )

@app.get("/logs/")
def get_logs(limit: int = 100):
    """Busca logs do MongoDB"""
    try:
        client = get_mongo_client()
        db = client.sistema_nosql
        collection = db.logs
        
        logs = list(collection.find().sort("timestamp", -1).limit(limit))
        
        # Converte ObjectId para string
        for log in logs:
            log["_id"] = str(log["_id"])
            if isinstance(log["timestamp"], datetime):
                log["timestamp"] = log["timestamp"].isoformat()
        
        logger.info(f"📋 Listando {len(logs)} logs do MongoDB")
        return {
            "success": True,
            "fallback_used": False,
            "logs": logs,
            "message": f"{len(logs)} logs encontrados"
        }
    except Exception as e:
        logger.error(f"❌ Erro ao acessar MongoDB: {e}")
        return {
            "success": False,
            "fallback_used": True,
            "logs": [],
            "message": f"MongoDB indisponível. Dados podem estar na fila: {FALLBACK_QUEUES['logs']}",
            "error": str(e)
        }

@app.post("/messages/")
def send_message(message: MessageCreate):
    try:
        success = rabbitmq.send_message(message.queue_name, message.message)
        if success:
            logger.info(f"📤 Mensagem enviada para {message.queue_name}")
            return {
                "success": True,
                "message": f"Mensagem enviada para {message.queue_name}",
                "queue_name": message.queue_name
            }
        else:
            raise HTTPException(status_code=500, detail="Erro ao enviar mensagem para RabbitMQ")
    except Exception as e:
        logger.error(f"❌ Erro ao enviar mensagem: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao enviar mensagem: {str(e)}")

# Worker automático para processar filas
import threading
import time

class FallbackWorker:
    def __init__(self, rabbitmq_client):
        self.rabbitmq = rabbitmq_client
        self.running = False
        self.worker_thread = None
        
    def start(self):
        """Inicia o worker automático"""
        if not self.running:
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info("🤖 Worker automático de fallback iniciado")
    
    def stop(self):
        """Para o worker automático"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join()
        logger.info("🛑 Worker automático de fallback parado")
    
    def _worker_loop(self):
        """Loop principal do worker"""
        while self.running:
            try:
                # Processa fila de usuários
                self._process_users_queue()
                
                # Processa fila de logs
                self._process_logs_queue()
                
                # Aguarda antes da próxima verificação
                time.sleep(30)  # Verifica a cada 30 segundos
                
            except Exception as e:
                logger.error(f"❌ Erro no worker de fallback: {e}")
                time.sleep(60)  # Aguarda mais em caso de erro
    
    def _process_users_queue(self):
        """Processa mensagens pendentes na fila de usuários"""
        queue_name = FALLBACK_QUEUES["users"]
        
        # Verifica se PostgreSQL está disponível
        if not check_database_health():
            return
        
        processed = 0
        while True:
            try:
                # Tenta receber mensagem da fila
                message = self.rabbitmq.receive_message(queue_name)
                if not message:
                    break
                
                # Processa a mensagem
                data = message.get("data", {})
                operation_type = message.get("operation_type", "unknown")
                
                if operation_type == "create_user":
                    success = self._create_user_from_queue(data)
                    if success:
                        processed += 1
                        logger.info(f"✅ Usuário processado da fila: {data.get('email')}")
                    else:
                        # Recoloca na fila com contador de retry
                        self._requeue_with_retry(queue_name, message)
                
            except Exception as e:
                logger.error(f"❌ Erro ao processar mensagem de usuário: {e}")
                break
        
        if processed > 0:
            logger.info(f"🔄 Processados {processed} usuários da fila de fallback")
    
    def _process_logs_queue(self):
        """Processa mensagens pendentes na fila de logs"""
        queue_name = FALLBACK_QUEUES["logs"]
        
        # Verifica se MongoDB está disponível
        try:
            client = get_mongo_client()
            client.admin.command("ping")
        except:
            return
        
        processed = 0
        while True:
            try:
                # Tenta receber mensagem da fila
                message = self.rabbitmq.receive_message(queue_name)
                if not message:
                    break
                
                # Processa a mensagem
                data = message.get("data", {})
                operation_type = message.get("operation_type", "unknown")
                
                if operation_type == "create_log":
                    success = self._create_log_from_queue(data)
                    if success:
                        processed += 1
                        logger.info(f"✅ Log processado da fila: {data.get('action')}")
                    else:
                        # Recoloca na fila com contador de retry
                        self._requeue_with_retry(queue_name, message)
                
            except Exception as e:
                logger.error(f"❌ Erro ao processar mensagem de log: {e}")
                break
        
        if processed > 0:
            logger.info(f"🔄 Processados {processed} logs da fila de fallback")
    
    def _create_user_from_queue(self, data: dict) -> bool:
        """Cria usuário no PostgreSQL a partir dos dados da fila"""
        try:
            db = get_session_with_retry(retries=2, delay=1)
            try:
                # Verifica se usuário já existe
                existing_user = db.query(User).filter(User.email == data["email"]).first()
                if existing_user:
                    logger.info(f"⚠️ Usuário já existe: {data['email']}")
                    return True  # Considera sucesso para remover da fila
                
                # Cria o usuário
                db_user = User(name=data["name"], email=data["email"])
                db.add(db_user)
                db.commit()
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Erro ao criar usuário da fila: {e}")
            return False
    
    def _create_log_from_queue(self, data: dict) -> bool:
        """Cria log no MongoDB a partir dos dados da fila"""
        try:
            client = get_mongo_client()
            db = client.sistema_nosql
            collection = db.logs
            
            log_entry = {
                "action": data["action"],
                "details": data["details"],
                "timestamp": datetime.now(),
                "processed_from_queue": True
            }
            
            result = collection.insert_one(log_entry)
            return bool(result.inserted_id)
            
        except Exception as e:
            logger.error(f"❌ Erro ao criar log da fila: {e}")
            return False
    
    def _requeue_with_retry(self, queue_name: str, message: dict):
        """Recoloca mensagem na fila com contador de retry"""
        retry_count = message.get("retry_count", 0) + 1
        max_retries = 5
        
        if retry_count <= max_retries:
            message["retry_count"] = retry_count
            message["last_retry"] = datetime.now().isoformat()
            
            self.rabbitmq.send_message(queue_name, message)
            logger.info(f"🔄 Mensagem recolocada na fila (tentativa {retry_count}/{max_retries})")
        else:
            # Envia para fila de erro após esgotar tentativas
            error_queue = f"{queue_name}_dead_letter"
            self.rabbitmq.send_message(error_queue, message)
            logger.error(f"💀 Mensagem enviada para fila de erro após {max_retries} tentativas")

# Instância do worker
fallback_worker = FallbackWorker(rabbitmq)

@app.get("/fallback/queues")
def get_fallback_queues():
    """Lista as filas de fallback configuradas"""
    return {
        "fallback_queues": FALLBACK_QUEUES,
        "worker_status": "running" if fallback_worker.running else "stopped",
        "status": "configured"
    }

@app.post("/fallback/worker/start")
def start_fallback_worker():
    """Inicia o worker automático de fallback"""
    fallback_worker.start()
    return {
        "success": True,
        "message": "Worker automático de fallback iniciado",
        "status": "running"
    }

@app.post("/fallback/worker/stop")
def stop_fallback_worker():
    """Para o worker automático de fallback"""
    fallback_worker.stop()
    return {
        "success": True,
        "message": "Worker automático de fallback parado",
        "status": "stopped"
    }

@app.post("/fallback/process/{queue_type}")
def process_fallback_queue(queue_type: str):
    """
    Processa dados pendentes na fila de fallback manualmente
    queue_type: 'users' ou 'logs'
    """
    if queue_type not in FALLBACK_QUEUES:
        raise HTTPException(status_code=400, detail=f"Tipo de fila inválido: {queue_type}")
    
    try:
        if queue_type == "users":
            fallback_worker._process_users_queue()
        elif queue_type == "logs":
            fallback_worker._process_logs_queue()
        
        return {
            "success": True,
            "queue_type": queue_type,
            "message": f"Processamento manual da fila {queue_type} executado"
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar fila {queue_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar fila: {str(e)}")

# Endpoint para debug
@app.get("/debug/db")
def debug_database():
    """Endpoint para debug da conexão com banco"""
    try:
        db = get_session_with_retry(retries=1, delay=1)
        try:
            result = db.execute(text("SELECT version(), current_database(), current_user")).fetchone()
            user_count = db.query(User).count()
            
            return {
                "status": "connected",
                "postgres_version": result[0] if result else "unknown",
                "database": result[1] if result else "unknown", 
                "user": result[2] if result else "unknown",
                "users_count": user_count
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ Debug database error: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/debug/fallback")
def debug_fallback():
    """Debug das filas de fallback e worker"""
    worker_info = {
        "running": fallback_worker.running,
        "thread_alive": fallback_worker.worker_thread.is_alive() if fallback_worker.worker_thread else False
    }
    
    return {
        "fallback_queues": FALLBACK_QUEUES,
        "rabbitmq_status": "connected" if (rabbitmq.connection and not rabbitmq.connection.is_closed) else "disconnected",
        "worker_status": worker_info
    }

@app.get("/fallback/stats")
def get_fallback_stats():
    """Estatísticas das filas de fallback"""
    stats = {}
    
    try:
        for queue_type, queue_name in FALLBACK_QUEUES.items():
            stats[queue_type] = {
                "queue_name": queue_name,
                "message_count": "N/A",  
                "status": "active"
            }
        
        return {
            "success": True,
            "worker_running": fallback_worker.running,
            "queues": stats
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "worker_running": fallback_worker.running
        }