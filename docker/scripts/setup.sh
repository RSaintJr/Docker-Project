
set -e  # Para o script se der erro

DEFAULT_SLEEP=15
SLEEP_TIME=${1:-$DEFAULT_SLEEP}

echo "🚀 Configurando Sistema de Containers - Arquitetura Integrada"
echo "============================================================"

if ! command -v docker &> /dev/null; then
    echo "❌ Docker não está instalado. Por favor, instale o Docker primeiro."
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose não está instalado ou não é compatível. Por favor, instale o Docker Compose v2+."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "❌ Você não tem permissão para rodar Docker. Adicione seu usuário ao grupo 'docker' ou use 'sudo'."
    exit 1
fi

echo "✅ Docker e Docker Compose detectados"

echo "🏗️  Parando containers existentes, se houver..."
docker compose down || true

echo "🏗️  Construindo e iniciando containers..."
docker compose up --build -d

echo "⏳ Aguardando inicialização dos serviços (${SLEEP_TIME}s)..."
sleep "$SLEEP_TIME"

echo "📊 Status dos containers:"
docker compose ps

echo ""
echo "🎉 Sistema iniciado com sucesso!"
echo ""
echo "🌐 Serviços disponíveis:"
echo "   • FastAPI (Backend): http://localhost:8000"
echo "   • FastAPI Docs: http://localhost:8000/docs"
echo "   • PostgreSQL: localhost:5432"
echo "   • MongoDB: localhost:27017"
echo "   • RabbitMQ Management: http://localhost:15672 (guest/guest)"
echo ""
echo "🔍 Para verificar logs:"
echo "   docker compose logs -f [nome_do_servico]"
echo ""
echo "🛑 Para parar o sistema:"
echo "   docker compose down"
echo ""
echo "🔄 Para reiniciar:"
echo "   docker compose restart"
