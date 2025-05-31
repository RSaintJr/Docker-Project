// Inicialização do MongoDB
db = db.getSiblingDB('sistema_nosql');

// Criar coleção de logs
db.createCollection('logs');

// Inserir dados de exemplo
db.logs.insertMany([
    {
        action: "system_startup",
        details: {
            message: "Sistema iniciado com sucesso",
            components: ["fastapi", "postgresql", "mongodb", "rabbitmq"]
        },
        timestamp: new Date()
    },
    {
        action: "database_init",
        details: {
            message: "Banco de dados inicializado",
            tables_created: ["users"]
        },
        timestamp: new Date()
    },
    {
        action: "sample_data",
        details: {
            message: "Dados de exemplo inseridos",
            count: 3
        },
        timestamp: new Date()
    }
]);

// Criar índices
db.logs.createIndex({ "timestamp": -1 });
db.logs.createIndex({ "action": 1 });

print("MongoDB inicializado com sucesso!");