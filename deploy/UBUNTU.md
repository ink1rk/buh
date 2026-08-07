# Установка на Ubuntu Server (виртуалка)

Минимальные требования: Ubuntu 22.04 / 24.04, 2 GB RAM, 2 vCPU, 10 GB диск.

## Быстрый способ (рекомендуется)

На сервере:

```bash
# 1. Склонировать репозиторий
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/ink1rk/buh.git
cd buh   # ветка main

# 2. Установить одной командой
sudo bash deploy/install-ubuntu.sh
```

Скрипт:
- ставит Docker
- собирает backend + frontend
- поднимает приложение на порту **80**
- создаёт systemd-сервис автозапуска
- открывает порт в UFW (если firewall активен)

После установки откройте в браузере:

```
http://IP_ВАШЕЙ_ВИРТУАЛКИ
```

## Опционально: OpenAI

```bash
sudo nano /opt/personal-finance-ai/.env
# добавьте:
# OPENAI_API_KEY=sk-...

cd /opt/personal-finance-ai
sudo docker compose -f docker-compose.prod.yml --env-file .env up -d
```

Без ключа приложение работает на локальном AI-fallback.

## Полезные команды

```bash
# Логи
cd /opt/personal-finance-ai
sudo docker compose -f docker-compose.prod.yml logs -f

# Статус
sudo docker compose -f docker-compose.prod.yml ps

# Остановить
sudo docker compose -f docker-compose.prod.yml down

# Обновить
sudo bash /opt/personal-finance-ai/deploy/update.sh

# Сменить порт (например 8080)
# в /opt/personal-finance-ai/.env поставьте APP_PORT=8080
# затем:
sudo docker compose -f docker-compose.prod.yml --env-file .env up -d
```

## Если порт 80 занят

```bash
APP_PORT=8080 sudo bash deploy/install-ubuntu.sh
```

## Firewall вручную

```bash
sudo ufw allow 80/tcp
sudo ufw allow OpenSSH
sudo ufw enable
```

## Бэкап данных

Данные лежат в Docker volume `finance_data`.

```bash
# Экспорт через API
curl -o backup.json http://127.0.0.1/api/v1/export/json

# Или бэкап volume
sudo docker run --rm -v personal-finance-ai_finance_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/finance-backup.tgz -C /data .
```

## Архитектура на сервере

```
браузер → :80 nginx (frontend)
              └─ /api/* → FastAPI backend
                            └─ SQLite volume
```
