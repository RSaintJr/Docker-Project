#!/bin/bash

echo "🌀 Iniciando consumidores automáticos para filas de fallback..."
echo "========================================"

consume_sql_fallback() {
    while true; do
        message=$(curl -s http://localhost:8000/messages/sql_fallback | jq -r '.message | @json')
        if [[ "$message" != "null" ]]; then
            name=$(echo $message | jq -r '.name')
            email=$(echo $message | jq -r '.email')

            echo "📥 Consumido da fila SQL: $name <$email>"

            curl -s -X POST http://localhost:8000/users/ \
                -H "Content-Type: application/json" \
                -d "{\"name\":\"$name\", \"email\":\"$email\"}" | jq .
        else
            sleep 2
        fi
    done
}

consume_nosql_fallback() {
    while true; do
        message=$(curl -s http://localhost:8000/messages/nosql_fallback | jq -r '.message | @json')
        if [[ "$message" != "null" ]]; then
            action=$(echo $message | jq -r '.action')
            details=$(echo $message | jq -c '.details')

            echo "📥 Consumido da fila NoSQL: $action"

            curl -s -X POST http://localhost:8000/logs/ \
                -H "Content-Type: application/json" \
                -d "{\"action\":\"$action\", \"details\":$details}" | jq .
        else
            sleep 2
        fi
    done
}

# Executar consumidores em paralelo
consume_sql_fallback &
consume_nosql_fallback &

echo "✅ Consumidores rodando... Pressione CTRL+C para parar."
wait
