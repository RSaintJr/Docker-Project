#!/bin/bash

set -e

echo "🧪 Testando API do Sistema de Containers - Arquitetura Integrada"
echo "==============================================================="

BASE_URL=${1:-"http://localhost:8000"}
TIMEOUT=${2:-10}
MAX_RETRIES=5

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função para log colorido
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Verificar se curl e jq estão instalados
check_dependencies() {
    local missing_deps=()
    
    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    fi
    
    if ! command -v jq &> /dev/null; then
        missing_deps+=("jq")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_error "Dependências faltando: ${missing_deps[*]}"
        log_info "Para instalar no Ubuntu/Debian: sudo apt-get update && sudo apt-get install curl jq"
        log_info "Para instalar no macOS: brew install curl jq"
        exit 1
    fi
}

# Aguardar API ficar disponível
wait_for_api() {
    log_info "Aguardando API ficar disponível em $BASE_URL..."
    
    for i in $(seq 1 $MAX_RETRIES); do
        if curl -s --max-time 5 "$BASE_URL/" > /dev/null 2>&1; then
            log_success "API está disponível!"
            return 0
        fi
        
        log_warning "Tentativa $i/$MAX_RETRIES: API não disponível, aguardando 3s..."
        sleep 3
    done
    
    log_error "API não ficou disponível após $MAX_RETRIES tentativas"
    exit 1
}

# Função para fazer requisições com tratamento de erro
make_request() {
    local method=$1
    local endpoint=$2
    local data=$3
    local description=${4:-"$method $endpoint"}
    
    echo ""
    log_info "$description"
    echo "➡️  $method $BASE_URL$endpoint"
    
    local http_code
    local response
    local temp_file=$(mktemp)
    
    if [ -n "$data" ]; then
        http_code=$(curl -s --max-time $TIMEOUT -w "%{http_code}" \
                         -X $method \
                         -H "Content-Type: application/json" \
                         -d "$data" \
                         -o "$temp_file" \
                         "$BASE_URL$endpoint")
    else
        http_code=$(curl -s --max-time $TIMEOUT -w "%{http_code}" \
                         -X $method \
                         -o "$temp_file" \
                         "$BASE_URL$endpoint")
    fi
    
    response=$(cat "$temp_file")
    rm "$temp_file"
    
    # Verificar se é JSON válido
    if echo "$response" | jq . >/dev/null 2>&1; then
        echo "$response" | jq .
    else
        echo "$response"
    fi
    
    # Verificar status HTTP
    case $http_code in
        200|201)
            log_success "Status: $http_code - Sucesso"
            ;;
        400|404|409)
            log_warning "Status: $http_code - Erro cliente"
            ;;
        500|503)
            log_error "Status: $http_code - Erro servidor"
            return 1
            ;;
        000)
            log_error "Status: Falha na conexão (timeout ou API indisponível)"
            return 1
            ;;
        *)
            log_warning "Status: $http_code - Resposta inesperada"
            ;;
    esac
    
    return 0
}

# Função para testar health check com detalhes
test_health_detailed() {
    log_info "Testando health check detalhado..."
    
    local health_response=$(curl -s --max-time $TIMEOUT "$BASE_URL/health")
    
    if echo "$health_response" | jq . >/dev/null 2>&1; then
        echo "$health_response" | jq .
        
        # Verificar status de cada serviço
        local postgres_status=$(echo "$health_response" | jq -r '.postgres // "UNKNOWN"')
        local mongo_status=$(echo "$health_response" | jq -r '.mongo // "UNKNOWN"')
        local rabbitmq_status=$(echo "$health_response" | jq -r '.rabbitmq // "UNKNOWN"')
        
        echo ""
        log_info "Status dos serviços:"
        [[ "$postgres_status" == "OK" ]] && log_success "PostgreSQL: $postgres_status" || log_warning "PostgreSQL: $postgres_status"
        [[ "$mongo_status" == "OK" ]] && log_success "MongoDB: $mongo_status" || log_warning "MongoDB: $mongo_status"
        [[ "$rabbitmq_status" == "OK" ]] && log_success "RabbitMQ: $rabbitmq_status" || log_warning "RabbitMQ: $rabbitmq_status"
    else
        log_error "Resposta do health check não é JSON válido"
        echo "$health_response"
    fi
}

# Função para criar usuário com validação
create_test_user() {
    local timestamp=$(date +%s)
    local email="teste_usuario_${timestamp}@example.com"
    
    make_request "POST" "/users/" "{
        \"name\": \"Teste Usuario $timestamp\",
        \"email\": \"$email\"
    }" "Criando usuário de teste"
    
    # Armazenar email para possível limpeza posterior
    echo "$email" > /tmp/test_user_email.txt
}

# Função para testar endpoint de debug
test_debug_endpoint() {
    log_info "Testando endpoint de debug do banco..."
    
    if make_request "GET" "/debug/db" "" "Debug da conexão PostgreSQL"; then
        log_success "Endpoint de debug funcionando"
    else
        log_warning "Endpoint de debug com problemas (pode não existir na versão atual)"
    fi
}

# Função para cleanup (opcional)
cleanup_test_data() {
    log_info "Limpeza de dados de teste não implementada"
    log_info "Para limpar manualmente, remova usuários de teste do PostgreSQL"
}

# Função principal de testes
run_tests() {
    local failed_tests=0
    local total_tests=0
    
    # Lista de testes
    declare -a tests=(
        "make_request GET / '' 'Verificando endpoint raiz'"
        "test_health_detailed"
        "create_test_user"
        "make_request GET /users/ '' 'Listando usuários'"
        "make_request POST /logs/ '{\"action\": \"test_action\", \"details\": {\"message\": \"Teste de log via API\", \"timestamp\": \"$(date -Iseconds)\"}}' 'Criando log de teste'"
        "make_request POST /messages/ '{\"queue_name\": \"test_queue\", \"message\": {\"type\": \"test\", \"content\": \"Mensagem de teste\", \"timestamp\": \"$(date -Iseconds)\"}}' 'Enviando mensagem para fila'"
        "test_debug_endpoint"
    )
    
    # Executar testes
    for test in "${tests[@]}"; do
        total_tests=$((total_tests + 1))
        echo ""
        echo "=================================================="
        log_info "Teste $total_tests: Executando teste..."
        echo "=================================================="
        
        if eval "$test"; then
            log_success "Teste $total_tests: PASSOU"
        else
            log_error "Teste $total_tests: FALHOU"
            failed_tests=$((failed_tests + 1))
        fi
    done
    
    # Resumo final
    echo ""
    echo "=================================================="
    echo "📊 RESUMO DOS TESTES"
    echo "=================================================="
    echo "Total de testes: $total_tests"
    echo "Sucessos: $((total_tests - failed_tests))"
    echo "Falhas: $failed_tests"
    
    if [ $failed_tests -eq 0 ]; then
        log_success "Todos os testes passaram! 🎉"
        return 0
    else
        log_error "$failed_tests teste(s) falharam"
        return 1
    fi
}

# Função de ajuda
show_help() {
    echo "Uso: $0 [BASE_URL] [TIMEOUT]"
    echo ""
    echo "Parâmetros:"
    echo "  BASE_URL  URL base da API (padrão: http://localhost:8000)"
    echo "  TIMEOUT   Timeout em segundos para requisições (padrão: 10)"
    echo ""
    echo "Exemplos:"
    echo "  $0                                    # URL padrão, timeout padrão"
    echo "  $0 http://localhost:8000              # URL específica"
    echo "  $0 http://localhost:8000 15           # URL e timeout específicos"
    echo ""
    echo "Variáveis de ambiente:"
    echo "  MAX_RETRIES  Número máximo de tentativas para conectar (padrão: 5)"
}

# Script principal
main() {
    # Verificar se foi solicitada ajuda
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
        show_help
        exit 0
    fi
    
    echo "🚀 Iniciando testes da API..."
    echo "URL: $BASE_URL"
    echo "Timeout: ${TIMEOUT}s"
    echo "Max Retries: $MAX_RETRIES"
    echo ""
    
    # Verificar dependências
    check_dependencies
    
    # Aguardar API
    wait_for_api
    
    # Executar testes
    if run_tests; then
        log_success "Todos os testes concluídos com sucesso! 🎉"
        exit 0
    else
        log_error "Alguns testes falharam"
        exit 1
    fi
}

# Executar apenas se script foi chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi