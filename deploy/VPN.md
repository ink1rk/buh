# WireGuard lite + Telegram MTProto

Скрипт `deploy/install-stack.sh` поднимает на Ubuntu **только**:

| Сервис | Порт | Назначение |
|--------|------|------------|
| WireGuard (native `wg-quick`, без панели) | `51820/udp` | VPN |
| mtg (FakeTLS MTProto) | `443/tcp` | прокси для Telegram |

Ни HTTP/SOCKS, ни приложение из этого репозитория на сервер не ставятся. Обычная прокся — отдельно, позже.

## Установка

```bash
sudo bash deploy/install-stack.sh
```

Клиенты WireGuard: `/root/vpn-clients/` (`laptop-full`, `phone-full`, split-варианты).

Ссылки Telegram: `/root/mtproto.txt`

## Firewall

Открыто только: `22/tcp`, `51820/udp`, `443/tcp`.
