#!/bin/bash

echo "🔧 Script de Correção - Sistema de Containers"
echo "============================================="

# Função para confirmar ação
confirm() {
    read -p "$1 (y/n): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

echo "1. 🛑 Parando todos os containers..."
docker-compose down 2>/dev/null || true

echo ""
echo "2. 🧹 Limpando sistema Docker..."
if confirm "Deseja limpar containers, imagens e volumes não utilizados?"; then
    docker system prune -af
    docker volume prune -f
    echo "✅ Sistema limpo!"
fi

echo ""
echo "3. 🔍 Verificando Docker daemon..."
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker daemon não está rodando"
    
    # Tentar iniciar Docker
    if confirm "Tentar iniciar o Docker?"; then
        if command -v systemctl >/dev/null 2>&1; then
            sudo systemctl start docker
        else
            sudo service docker start
        fi
        
        sleep 3
        
        if docker info >/dev/null 2>&1; then
            echo "✅ Docker iniciado com sucesso!"
        else
            echo "❌ Falha ao iniciar Docker. Verifique manualmente."
            exit 1
        fi
    else
        exit 1
    fi
fi

echo ""
echo "4. 🔧 Configurações específicas para WSL2..."
if grep -qEi "(Microsoft|WSL)" /proc/version 2>/dev/null; then
    echo "🐧 WSL2 detectado - Aplicando correções..."
    
    # Verificar se o script start-docker.sh existe
    if [ -f ~/start-docker.sh ]; then
        echo "📝 Executando script de inicialização WSL2..."
        ~/start-docker.sh
    fi
    
    # Configurar DOCKER_HOST se necessário
    if [ -z "$DOCKER_HOST" ]; then
        export DOCKER_HOST=unix:///var/run/docker.sock
        echo "export DOCKER_HOST=unix:///var/run/docker.sock" >> ~/.bashrc
        echo "✅ DOCKER_HOST configurado"
    fi
fi

echo ""
echo "5. 🐳 Verificando docker-compose.yml..."
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml não encontrado!"
    echo "💡 Certifique-se de estar no diretório correto do projeto"
    exit 1
fi

# Verificar sintaxe do docker-compose.yml
if docker-compose config >/dev/null 2>&1; then
    echo "✅ docker-compose.yml válido"
else
    echo "❌ Erro na sintaxe do docker-compose.yml"
    echo "Executando diagnóstico:"
    docker-compose config
    exit 1
fi

echo ""
echo "6. 🏗️  Reconstruindo containers..."
echo "Isso pode levar alguns minutos..."

# Construir imagens sem cache
docker-compose build --no-cache

echo ""
echo "7. 🚀 Iniciando containers..."
docker-compose up -d

echo ""
echo "8. ⏳ Aguardando inicialização (30 segundos)..."
sleep 30

echo ""
echo "9. 📊 Verificando status..."
docker-compose ps

echo ""
echo "10. 🌐 Testando conectividade..."

# Tentar diferentes endereços
ENDPOINTS=("http://localhost:8000" "http://127.0.0.1:8000" "http://0.0.0.0:8000")

for endpoint in "${ENDPOINTS[@]}"; do
    echo "Testando $endpoint..."
    if command -v curl >/dev/null 2>&1; then
        if curl -s --max-time 5 "$endpoint" >/dev/null 2>&1; then
            echo "✅ $endpoint está respondendo!"
        else
            echo "❌ $endpoint não responde"
        fi
    fi
done

echo ""
echo "11. 📋 Logs recentes dos serviços..."
echo "=================================="
docker-compose logs --tail=10

echo ""
echo "🎯 Próximos passos:"
echo "=================="
echo "1. Acesse: http://localhost:8000/docs"
echo "2. Se ainda não funcionar, execute: ./docker_diagnostic.sh"
echo "3. Verifique logs específicos: docker-compose logs -f [serviço]"
echo ""

# Verificar portas ocupadas
echo "🔌 Verificando se as portas estão sendo usadas:"
if command -v netstat >/dev/null 2>&1; then
    netstat -tlnp | grep -E ':(8000|5432|27017|15672)' || echo "Nenhuma porta do sistema ocupada"
elif command -v ss >/dev/null 2>&1; then
    ss -tlnp | grep -E ':(8000|5432|27017|15672)' || echo "Nenhuma porta do sistema ocupada"
fi

echo ""
echo "✨ Script de correção concluído!"
echo "Se ainda tiver problemas, execute o diagnóstico completo."