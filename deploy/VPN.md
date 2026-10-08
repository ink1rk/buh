# wg-easy + Telegram MTProto

Скрипт `deploy/install-stack.sh` поднимает на Ubuntu:

| Сервис | Порт | Назначение |
|--------|------|------------|
| **wg-easy** (Emile Nijssen) | UI `51821/tcp`, WG `51820/udp` | панель и VPN |
| mtg (FakeTLS MTProto) | `443/tcp` | прокси для Telegram |

Ни HTTP/SOCKS, ни приложение из этого репозитория не ставятся.

## Панель

Открой `http://IP:51821` → создай админа → Host = публичный IP, Port = `51820`.

Клиенты: **New Client** → QR на телефон или скачать `.conf` на ноут.

Старые native `wg-quick` конфиги после перехода на панель не работают — ключи сервера новые.

## Установка

```bash
sudo bash deploy/install-stack.sh
```

Ссылки Telegram: `/root/mtproto.txt`

## Firewall

`22/tcp`, `51820/udp`, `51821/tcp`, `443/tcp`.
