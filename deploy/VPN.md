# WireGuard + прокси + приложение

Скрипт `deploy/install-stack.sh` поднимает на Ubuntu 22.04/24.04 полный стек для небольшой VPS (1 GB RAM хватает):

| Сервис | Где слушает | Кто может ходить |
|--------|-------------|------------------|
| WireGuard | `0.0.0.0:51820/udp` | интернет |
| Приложение (nginx → FastAPI) | `:80` | интернет и WG-клиенты |
| HTTP-прокси (tinyproxy) | `10.8.0.1:3128` | только `10.8.0.0/24` |
| SOCKS5 (microsocks) | `10.8.0.1:1080` | только `10.8.0.0/24` |
| Backend | `127.0.0.1:8000` | только localhost |

Через WireGuard full-tunnel весь трафик клиента идёт через VPS (NAT). Split-tunnel открывает только `10.8.0.0/24` — приложение и прокси.

## Установка

```bash
sudo bash deploy/install-stack.sh
```

Клиентские конфиги: `/root/vpn-clients/`

- `laptop-full.conf` / `phone-full.conf` — весь интернет через VPS
- `laptop-split.conf` / `phone-split.conf` — только VPN-сеть

Импорт в [WireGuard](https://www.wireguard.com/install/) (телефон: QR из `qrencode -t ansiutf8 < /root/vpn-clients/phone-full.conf`).

После подключения:

```
Приложение:   http://10.8.0.1/
HTTP proxy:   10.8.0.1:3128
SOCKS5:       10.8.0.1:1080
```

Чтобы закрыть приложение с публичного IP и оставить только VPN:

```bash
sudo ufw delete allow 80/tcp
sudo ufw status
```

## Полезные команды

```bash
sudo wg show
sudo systemctl status wg-quick@wg0 pfa nginx tinyproxy microsocks
sudo journalctl -u pfa -f
```
