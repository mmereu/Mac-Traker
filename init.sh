#!/bin/bash

# Mac-Traker - Network Intelligence for MAC Address Tracking
# Initialization Script

set -e

echo "========================================"
echo "  Mac-Traker - Initialization Script"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
check_prerequisites() {
    echo -e "\n${YELLOW}Checking prerequisites...${NC}"

    # Check Python
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
        echo -e "${GREEN}[OK]${NC} Python $PYTHON_VERSION"
    else
        echo -e "${RED}[ERROR]${NC} Python 3.11+ required but not found"
        exit 1
    fi

    # Check Node.js
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version)
        echo -e "${GREEN}[OK]${NC} Node.js $NODE_VERSION"
    else
        echo -e "${RED}[ERROR]${NC} Node.js 18+ required but not found"
        exit 1
    fi

    # Check npm
    if command -v npm &> /dev/null; then
        NPM_VERSION=$(npm --version)
        echo -e "${GREEN}[OK]${NC} npm $NPM_VERSION"
    else
        echo -e "${RED}[ERROR]${NC} npm required but not found"
        exit 1
    fi

    # Check PostgreSQL (optional warning)
    if command -v psql &> /dev/null; then
        PSQL_VERSION=$(psql --version 2>&1 | head -n1)
        echo -e "${GREEN}[OK]${NC} $PSQL_VERSION"
    else
        echo -e "${YELLOW}[WARN]${NC} PostgreSQL not found - ensure database is accessible"
    fi
}

# Setup backend
setup_backend() {
    echo -e "\n${YELLOW}Setting up backend...${NC}"

    cd backend

    # Create virtual environment if not exists
    if [ ! -d "venv" ]; then
        echo "Creating Python virtual environment..."
        python3 -m venv venv
    fi

    # Activate virtual environment
    source venv/bin/activate

    # Install dependencies
    echo "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt

    # Create .env if not exists
    if [ ! -f ".env" ]; then
        echo "Creating .env from template..."
        cp .env.example .env
        echo -e "${YELLOW}[ACTION REQUIRED]${NC} Edit backend/.env with your configuration"
    fi

    cd ..
    echo -e "${GREEN}[OK]${NC} Backend setup complete"
}

# Setup frontend
setup_frontend() {
    echo -e "\n${YELLOW}Setting up frontend...${NC}"

    cd frontend

    # Install dependencies
    echo "Installing Node.js dependencies..."
    npm install

    cd ..
    echo -e "${GREEN}[OK]${NC} Frontend setup complete"
}

# Setup database
setup_database() {
    echo -e "\n${YELLOW}Setting up database...${NC}"

    cd backend
    source venv/bin/activate

    # Run migrations
    echo "Running database migrations..."
    alembic upgrade head || echo -e "${YELLOW}[WARN]${NC} Migration failed - check database connection"

    cd ..
    echo -e "${GREEN}[OK]${NC} Database setup complete"
}

# Start services
start_services() {
    echo -e "\n${YELLOW}Starting services...${NC}"

    # Start backend in background
    echo "Starting backend server..."
    cd backend
    source venv/bin/activate
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
    BACKEND_PID=$!
    cd ..

    # Start frontend in background
    echo "Starting frontend server..."
    cd frontend
    npm run dev &
    FRONTEND_PID=$!
    cd ..

    echo -e "\n${GREEN}========================================"
    echo "  Mac-Traker is running!"
    echo "========================================"
    echo -e "${NC}"
    echo "  Frontend: http://localhost:5173"
    echo "  Backend:  http://localhost:8000"
    echo "  API Docs: http://localhost:8000/docs"
    echo ""
    echo "  Press Ctrl+C to stop all services"
    echo ""

    # Wait for processes
    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
    wait
}

# Main execution
main() {
    check_prerequisites

    # Parse arguments
    case "${1:-all}" in
        "check")
            echo -e "\n${GREEN}All prerequisites OK${NC}"
            ;;
        "backend")
            setup_backend
            ;;
        "frontend")
            setup_frontend
            ;;
        "db")
            setup_database
            ;;
        "start")
            start_services
            ;;
        "all"|*)
            setup_backend
            setup_frontend
            setup_database
            echo -e "\n${GREEN}Setup complete!${NC}"
            echo "Run './init.sh start' to start the application"
            ;;
    esac
}

main "$@"
