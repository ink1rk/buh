# Personal Finance AI

Премиальный личный финансовый штаб — не бухгалтерия, а советник, аналитик и мотиватор.

Вдохновение: Apple, Arc, Linear, Raycast, Revolut, Copilot Money.

## Установка на Ubuntu Server (виртуалка)

Самый простой способ:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/ink1rk/buh.git
cd buh
sudo bash deploy/install-ubuntu.sh
```

После установки откройте `http://IP_СЕРВЕРА` в браузере.

Подробности: [deploy/UBUNTU.md](deploy/UBUNTU.md)

```bash
# другой порт
APP_PORT=8080 sudo bash deploy/install-ubuntu.sh

# с OpenAI
OPENAI_API_KEY=sk-... sudo bash deploy/install-ubuntu.sh
```

## Стек

**Frontend:** React · TypeScript · TailwindCSS · Framer Motion · Plotly · TanStack Query · Zustand · React Router

**Backend:** FastAPI · SQLAlchemy · Alembic · SQLite · Pydantic · OpenAI-compatible LLM · ChromaDB (опционально) · OCR/Vision

## Локальная разработка

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

UI: http://127.0.0.1:5173

### Docker (dev)

```bash
docker compose up --build
```

### Docker (production, как на Ubuntu)

```bash
cp .env.production.example .env
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

## Возможности

- Живой dashboard: Net Worth, proactive AI, AI Coach, streak
- Financial Health Score + психолог паттернов
- Spotlight быстрый ввод (`⌘K`)
- AI Timeline, карта капитала, contribution graph
- Habits / Risks / Happiness Index
- AI спорит с покупками + Financial Twin
- Forecast, scenarios, OCR, gamification
- Dark / Light / Auto тема, glassmorphism UI

## Архитектура

```
backend/app/   — API, AI, OCR, analytics, capital, coach…
frontend/src/  — UI screens & design system
deploy/        — Ubuntu Server installer + nginx
database/      — SQLite (локально) / Docker volume (prod)
```

## Безопасность

Данные локально в SQLite. На сервере — Docker volume `finance_data`.  
Экспорт: CSV / Excel / JSON через UI или `/api/v1/export/*`.
