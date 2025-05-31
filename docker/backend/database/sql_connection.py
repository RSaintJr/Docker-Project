from sqlalchemy import create_engine, Column, Integer, String, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:postgres@postgres:5432/sistema_db"
)

# Pool settings para melhor gerenciamento de conexões
engine_kwargs = {
    'pool_size': 10,
    'max_overflow': 20,
    'pool_pre_ping': True,  # Verifica conexões antes de usar
    'pool_recycle': 3600,   # Recicla conexões a cada hora
}

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

def get_engine():
    return create_engine(DATABASE_URL, **engine_kwargs)

def get_session():
    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

def test_connection(engine):
    """Testa a conexão com o banco"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error(f"Erro na conexão: {e}")
        return False

def get_session_with_retry(retries=10, delay=2):
    """Obtém sessão com retry e backoff exponencial"""
    engine = get_engine()
    
    for attempt in range(1, retries + 1):
        try:
            # Testa a conexão primeiro
            if test_connection(engine):
                SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
                session = SessionLocal()
                logger.info("✅ Conectado ao PostgreSQL com sucesso!")
                return session
            else:
                raise Exception("Falha no teste de conexão")
                
        except Exception as e:
            logger.warning(f"🚨 Tentativa {attempt}/{retries}: falha ao conectar ao PostgreSQL: {e}")
            
            if attempt == retries:
                logger.error("❌ Não conseguiu conectar ao PostgreSQL após todas as tentativas.")
                raise Exception(f"❌ Não conseguiu conectar ao PostgreSQL após {retries} tentativas. Último erro: {e}")
            
            # Backoff exponencial: 2, 4, 8, 16... segundos (máximo 30s)
            sleep_time = min(delay * (2 ** (attempt - 1)), 30)
            logger.info(f"⏳ Aguardando {sleep_time}s antes da próxima tentativa...")
            time.sleep(sleep_time)

def create_tables():
    """Cria as tabelas no banco"""
    max_retries = 10
    for attempt in range(1, max_retries + 1):
        try:
            engine = get_engine()
            
            # Testa conexão primeiro
            if not test_connection(engine):
                raise Exception("Falha no teste de conexão")
            
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Tabelas criadas/verificadas com sucesso!")
            return
            
        except Exception as e:
            logger.warning(f"🚨 Tentativa {attempt}/{max_retries} de criar tabelas: {e}")
            
            if attempt == max_retries:
                logger.error("❌ Falha ao criar tabelas após todas as tentativas.")
                raise
            
            sleep_time = min(2 * attempt, 30)
            logger.info(f"⏳ Aguardando {sleep_time}s antes da próxima tentativa...")
            time.sleep(sleep_time)

def check_database_health():
    """Verifica se o banco está saudável"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
        return True
    except:
        return False