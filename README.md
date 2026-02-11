# Mac-Traker

Sistema di Network Intelligence per il tracking dei MAC address in ambienti enterprise.

Network Intelligence system for MAC address tracking in enterprise environments.

---

## Panoramica / Overview

### IT

Mac-Traker analizza 1200+ dispositivi di rete (99% Huawei, 1% Cisco, AP Extreme) per:
- Localizzare con certezza al 100% l'endpoint fisico di ogni MAC address
- Tracciare movimenti storici dei dispositivi
- Mappare la topologia di rete
- Generare alert in tempo reale

### EN

Mac-Traker analyzes 1200+ network devices (99% Huawei, 1% Cisco, Extreme APs) to:
- Locate with 100% certainty the physical endpoint of every MAC address
- Track historical device movements
- Map network topology
- Generate real-time alerts

---

## Features Principali / Key Features

### Ricerca MAC / MAC Search
- Ricerca per MAC completo o parziale / Search by full or partial MAC
- Ricerca per IP o hostname / Search by IP or hostname
- Tempo risposta < 2 secondi / Response time < 2 seconds
- Certezza 100% endpoint fisico / 100% physical endpoint certainty

### Discovery Rete / Network Discovery
- SNMP primario (Bridge MIB) / SNMP primary (Bridge MIB)
- SSH fallback per dispositivi problematici / SSH fallback for problematic devices
- Scheduling configurabile (15-30 min) / Configurable scheduling (15-30 min)
- Supporto Huawei, Cisco, Extreme / Huawei, Cisco, Extreme support

### Topology Mapping
- Mappa interattiva della rete / Interactive network map
- Discovery LLDP/CDP / LLDP/CDP discovery
- Click su switch per vedere MAC connessi / Click on switch to see connected MACs
- Highlight percorso MAC / MAC path highlight

### Alerting
- Nuovo MAC rilevato / New MAC detected
- MAC cambia porta / MAC changes port
- MAC scompare / MAC disappears
- Porta con troppi MAC / Port with too many MACs
- Notifiche Telegram / Telegram notifications

---

## Stack Tecnologico / Tech Stack

### Backend
- Python 3.11+
- FastAPI
- PostgreSQL
- SQLAlchemy 2.0
- pysnmp / netmiko
- APScheduler

### Frontend
- React 18+
- TypeScript
- Vite
- TailwindCSS
- Recharts
- vis.js / D3.js

---

## Prerequisiti / Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Accesso SNMP ai dispositivi di rete / SNMP access to network devices
- Credenziali SSH per CLI fallback / SSH credentials for CLI fallback
- Bot Telegram (opzionale, per alert) / Telegram bot (optional, for alerts)

## Installazione / Installation

```bash
git clone https://github.com/mmereu/Mac-Traker.git
cd Mac-Traker

# Setup completo / Full setup (backend + frontend + database)
./init.sh

# Oppure setup singole componenti / Or setup single components
./init.sh backend   # Solo backend / Backend only
./init.sh frontend  # Solo frontend / Frontend only
./init.sh db        # Solo database migrations / Database migrations only
```

## Configurazione / Configuration

1. Copia il file di configurazione / Copy the configuration file:
```bash
cp backend/.env.example backend/.env
```

2. Modifica `backend/.env` / Edit `backend/.env`:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/mactraker
SNMP_COMMUNITY=public
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id
```

## Avvio / Start

```bash
# Avvia tutti i servizi / Start all services
./init.sh start
```

Oppure avvia manualmente / Or start manually:

```bash
# Backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload

# Frontend (in un altro terminale / in another terminal)
cd frontend
npm run dev
```

## Accesso / Access

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **API Docs (ReDoc)**: http://localhost:8000/redoc

---

## Struttura del Progetto / Project Structure

```
Mac-Traker/
├── backend/                 # FastAPI Backend
│   ├── app/
│   │   ├── api/            # API endpoints
│   │   ├── core/           # Configuration, security
│   │   ├── db/             # Database models, sessions
│   │   ├── services/       # Business logic
│   │   │   ├── discovery/  # SNMP/SSH discovery
│   │   │   ├── alerts/     # Alert management
│   │   │   └── topology/   # Topology mapping
│   │   └── main.py         # FastAPI app
│   ├── alembic/            # Database migrations
│   ├── requirements.txt
│   └── .env.example
├── frontend/               # React Frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── pages/          # Page components
│   │   ├── services/       # API clients
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
├── init.sh                 # Setup script
└── README.md
```

## API Reference

Documentazione completa disponibile su / Full documentation available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Licenza / License

MIT License - vedi [LICENSE](LICENSE) / see [LICENSE](LICENSE)
