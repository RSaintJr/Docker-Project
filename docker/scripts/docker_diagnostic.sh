
echo "🔍 Diagnóstico do Sistema de Containers"
echo "======================================"

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo "1. 🐳 Verificando Docker..."
if command_exists docker; then
    echo "✅ Docker está instalado"
    docker --version
    
    if docker info >/dev/null 2>&1; then
        echo "✅ Docker daemon está rodando"
    else
        echo "❌ Docker daemon não está rodando"
        echo "💡 Execute: sudo service docker start"
        exit 1
    fi
else
    echo "❌ Docker não está instalado"
    exit 1
fi

echo ""
echo "2. 🐙 Verificando Docker Compose..."
if command_exists docker-compose; then
    echo "✅ Docker Compose está instalado"
    docker-compose --version
elif command_exists docker && docker compose version >/dev/null 2>&1; then
    echo "✅ Docker Compose (plugin) está disponível"
    docker compose version
else
    echo "❌ Docker Compose não está disponível"
    exit 1
fi

echo ""
echo "3. 📁 Verificando arquivos necessários..."
if [ -f "docker-compose.yml" ]; then
    echo "✅ docker-compose.yml encontrado"
else
    echo "❌ docker-compose.yml não encontrado"
    echo "💡 Certifique-se de estar no diretório correto do projeto"
    exit 1
fi

echo ""
echo "4. 📊 Status atual dos containers..."
docker-compose ps

echo ""
echo "5. 🔌 Verificando portas ocupadas..."
echo "Porta 8000 (FastAPI):"
if command_exists netstat; then
    netstat -tlnp | grep :8000 || echo "Porta 8000 livre"
elif command_exists ss; then
    ss -tlnp | grep :8000 || echo "Porta 8000 livre"
else
    echo "Comandos netstat/ss não disponíveis"
fi

echo ""
echo "Porta 5432 (PostgreSQL):"
if command_exists netstat; then
    netstat -tlnp | grep :5432 || echo "Porta 5432 livre"
elif command_exists ss; then
    ss -tlnp | grep :5432 || echo "Porta 5432 livre"
fi

echo ""
echo "6. 📋 Logs dos containers (últimas 20 linhas)..."
echo "=================================="

CONTAINERS=$(docker-compose ps --services 2>/dev/null)

if [ -n "$CONTAINERS" ]; then
    for container in $CONTAINERS; do
        echo ""
        echo "--- Logs do $container ---"
        docker-compose logs --tail=20 $container 2>/dev/null || echo "Sem logs disponíveis"
    done
else
    echo "Nenhum container rodando"
fi

echo ""
echo "7. 🌐 Testando conectividade..."
echo "================================"

if docker-compose ps | grep -q "Up.*8000"; then
    echo "Container do backend está UP na porta 8000"
    
    echo "Testando conexão interna ao backend..."
    
    if docker-compose exec backend wget -q --spider http://localhost:8000 2>/dev/null; then
        echo "✅ Backend responde internamente (wget)"
    elif docker-compose exec backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000')" 2>/dev/null; then
        echo "✅ Backend responde internamente (python)"
    elif docker-compose exec backend nc -z localhost 8000 2>/dev/null; then
        echo "✅ Backend porta 8000 está aberta internamente (netcat)"
    else
        echo "❌ Backend não responde internamente (testado wget, python, netcat)"
    fi
    
    echo "Testando conexão externa ao backend..."
    if command -v curl >/dev/null 2>&1; then
        if curl -s --max-time 5 http://localhost:8000 >/dev/null 2>&1; then
            echo "✅ Backend responde externamente (curl)"
        else
            echo "❌ Backend não responde externamente (curl)"
        fi
    elif command -v wget >/dev/null 2>&1; then
        if wget -q --timeout=5 --tries=1 --spider http://localhost:8000 2>/dev/null; then
            echo "✅ Backend responde externamente (wget)"
        else
            echo "❌ Backend não responde externamente (wget)"
        fi
    elif command -v nc >/dev/null 2>&1; then
        if nc -z localhost 8000 2>/dev/null; then
            echo "✅ Porta 8000 está aberta externamente (netcat)"
        else
            echo "❌ Porta 8000 não está acessível externamente (netcat)"
        fi
    else
        echo "⚠️ Nenhum comando de teste disponível (curl, wget, nc)"
    fi
else
    echo "❌ Container do backend não está rodando na porta 8000"
fi

echo ""
echo "8. 🔧 Sugestões de solução..."
echo "============================"

if grep -qEi "(Microsoft|WSL)" /proc/version 2>/dev/null; then
    echo "🐧 Detectado WSL2 - Verificações específicas:"
    echo "   • Certifique-se de que o Docker Desktop está rodando no Windows"
    echo "   • Verifique se WSL2 integration está ativada no Docker Desktop"
    echo "   • Execute: sudo service docker restart"
fi

echo ""
echo "💡 Passos recomendados para resolver:"
echo "   1. Parar todos os containers: docker-compose down"
echo "   2. Limpar sistema: docker system prune -f"
echo "   3. Reconstruir: docker-compose up --build -d"
echo "   4. Verificar logs: docker-compose logs -f"
echo ""
echo "🆘 Se ainda tiver problemas:"
echo "   • Verifique o arquivo docker-compose.yml"
echo "   • Certifique-se de que não há firewall bloqueando"
echo "   • Tente acessar: http://127.0.0.1:8000 ao invés de localhost"