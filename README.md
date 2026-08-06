# Personal Finance AI

Премиальный личный финансовый штаб — не бухгалтерия, а советник, аналитик и мотиватор.

Вдохновение: Apple, Arc, Linear, Raycast, Revolut, Copilot Money.

## Стек

**Frontend:** React · TypeScript · TailwindCSS · Framer Motion · Plotly · TanStack Query · Zustand · React Router

**Backend:** FastAPI · SQLAlchemy · Alembic · SQLite · Pydantic · OpenAI-compatible LLM · ChromaDB (опционально) · OCR/Vision

## Быстрый старт

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # опционально: OPENAI_API_KEY
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

### Docker

```bash
docker compose up --build
```

## Возможности

- Dashboard с приветствием, мыслью дня, Widget of the Day, Financial Health Score
- Spotlight быстрый ввод (`⌘K`): `+50000 зарплата`, `-1200 пятерочка`, долги, инвестиции
- AI-чат справа (локальный интеллект + OpenAI при наличии ключа)
- Цели, долги, подписки, календарь, инвестиции-советник
- Аналитика Plotly: timeseries, heatmap, treemap, radar, sankey, forecast
- Сценарии «что если», AI Purchase Analyzer, OCR чеков
- Gamification, AI Memory (SQLite + ChromaDB), экспорт CSV/Excel/JSON
- Dark / Light / Auto тема, glassmorphism UI

## Архитектура

```
backend/app/
  api/           # HTTP routes
  ai/            # advisor + memory
  ocr/           # receipt vision
  investment/    # portfolio advice
  services/      # domain engines
  models/        # SQLAlchemy
  schemas/       # Pydantic
frontend/src/
  components/    # UI, layout, AI, OCR
  pages/         # screens
  store/         # Zustand
  lib/           # api + utils
database/        # SQLite + chroma
```

## Безопасность

Данные хранятся локально в SQLite (`database/finance.db`).  
Опционально: `ENCRYPTION_KEY` для полевого шифрования, бэкапы через экспорт.

## Demo

При первом запуске backend сидирует профиль **Кирилл** с реалистичными счетами, целями, транзакциями и insights.
