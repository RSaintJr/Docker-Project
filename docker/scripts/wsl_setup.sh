#!/bin/bash

echo "🐧 Configuração WSL2 para Sistema de Containers"
echo "=============================================="

# Verificar se está no WSL
if ! grep -qEi "(Microsoft|WSL)" /proc/version &> /dev/null; then
    echo "⚠️  Este script é otimizado para WSL2. Continue mesmo assim? (y/n)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "🔍 Verificando sistema..."

# Atualizar sistema
echo "📦 Atualizando sistema..."
sudo apt update && sudo apt upgrade -y

# Instalar dependências básicas
echo "🛠️  Instalando dependências básicas..."
sudo apt install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    net-tools \
    jq \
    unzip

# Verificar se Docker já está instalado
if command -v docker &> /dev/null; then
    echo "✅ Docker já está instalado"
    docker --version
else
    echo "🐳 Instalando Docker..."
    
    # Remover versões antigas
    sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
    
    # Instalar Docker
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    
    # Adicionar usuário ao grupo docker
    sudo usermod -aG docker $USER
    
    echo "✅ Docker instalado com sucesso!"
fi

# Verificar Docker Compose
if command -v docker-compose &> /dev/null; then
    echo "✅ Docker Compose já está instalado"
    docker-compose --version
else
    echo "🐙 Instalando Docker Compose..."
    
    # Instalar Docker Compose
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | jq -r '.tag_name')
    sudo curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    
    # Criar link simbólico se necessário
    sudo ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
    
    echo "✅ Docker Compose instalado com sucesso!"
fi

# Configurar Docker para WSL2
echo "⚙️  Configurando Docker para WSL2..."

# Criar arquivo daemon.json se não existir
sudo mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
    sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
    "hosts": ["unix:///var/run/docker.sock"],
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2"
}
EOF
fi

# Configurar systemctl para WSL2 (se necessário)
if ! systemctl is-active --quiet docker 2>/dev/null; then
    echo "🔧 Configurando serviço Docker..."
    
    # Para WSL2, Docker pode precisar ser iniciado manualmente
    if grep -qi wsl /proc/version; then
        echo "📝 Criando script de inicialização para WSL2..."
        
        # Criar script para iniciar Docker no WSL2
        cat > ~/start-docker.sh << 'EOF'
#!/bin/bash
echo "🐳 Iniciando Docker no WSL2..."
sudo service docker start
echo "✅ Docker iniciado!"
EOF
        chmod +x ~/start-docker.sh
        
        echo "💡 Para iniciar Docker no WSL2, execute: ~/start-docker.sh"
    fi
fi

# Verificar instalação
echo "🧪 Verificando instalação..."

# Tentar iniciar Docker
if command -v systemctl &> /dev/null; then
    sudo systemctl start docker 2>/dev/null || sudo service docker start 2>/dev/null || true
else
    sudo service docker start 2>/dev/null || true
fi

sleep 3

# Testar Docker
if docker run --rm hello-world &>/dev/null; then
    echo "✅ Docker funcionando corretamente!"
else
    echo "⚠️  Docker pode precisar ser reiniciado"
    echo "💡 Execute: sudo service docker restart"
fi

# Configurações adicionais do WSL2
echo "🔧 Configurações adicionais do WSL2..."

# Configurar Git (se não configurado)
if [ -z "$(git config --global user.name)" ]; then
    echo "📝 Configurando Git..."
    echo "Digite seu nome:"
    read -r git_name
    echo "Digite seu email:"
    read -r git_email
    
    git config --global user.name "$git_name"
    git config --global user.email "$git_email"
    echo "✅ Git configurado!"
fi

# Configurar aliases úteis
echo "⚡ Configurando aliases úteis..."
cat >> ~/.bashrc << 'EOF'

# Docker aliases
alias dps='docker ps'
alias dimg='docker images'
alias dlog='docker logs'
alias dexec='docker exec -it'
alias dcp='docker-compose'
alias dcup='docker-compose up -d'
alias dcdown='docker-compose down'
alias dclog='docker-compose logs -f'

# Sistema aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'

# Função para limpar Docker
docker-clean() {
    docker system prune -af
    docker volume prune -f
}
EOF

# Configurar variáveis de ambiente
echo "🌐 Configurando variáveis de ambiente..."
cat >> ~/.bashrc << 'EOF'

# WSL2 Docker environment
export DOCKER_HOST=unix:///var/run/docker.sock

# Otimizações WSL2
export WSLENV=DOCKER_HOST/up
EOF

# Criar diretório de projetos
mkdir -p ~/projetos
cd ~/projetos

echo ""
echo "🎉 Configuração WSL2 concluída com sucesso!"
echo ""
echo "📋 Próximos passos:"
echo "   1. Reiniciar terminal: exit && wsl"
echo "   2. Ou executar: source ~/.bashrc"
echo "   3. Verificar Docker: docker run hello-world"
echo "   4. Se necessário, iniciar Docker: ~/start-docker.sh"
echo ""
echo "💡 Aliases disponíveis:"
echo "   dps, dimg, dlog, dexec, dcp, dcup, dcdown, dclog"
echo ""
echo "📁 Diretório de projetos criado em: ~/projetos"
echo ""
echo "🚀 Para baixar o projeto do Sistema de Containers:"
echo "   cd ~/projetos"
echo "   git clone <url-do-repositorio>"
echo "   cd sistema-containers"
echo "   ./setup.sh"