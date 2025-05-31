-- Inicialização do banco PostgreSQL
CREATE DATABASE IF NOT EXISTS sistema_db;

-- Conectar ao banco sistema_db
\c sistema_db;

-- Criar extensões úteis
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Criar tabela de usuários (será criada automaticamente pelo SQLAlchemy)
-- Mas vamos garantir que existe
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inserir dados de exemplo
INSERT INTO users (name, email) VALUES 
('Roberto Santos', 'roberto@ifc.edu.br'),
('Maria Silva', 'maria@example.com'),
('João Costa', 'joao@example.com')
ON CONFLICT (email) DO NOTHING;

-- Criar índices para performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);