# Appliance ITMS

Это заготовка установщика, а не собранный ISO. Образ `ITMS-Appliance-*.iso` здесь не публикуется: в этой среде нет прогона `lb build` и проверки в QEMU.

ITMS остаётся веб-стеком из `itms/deploy` (Docker Compose). Отдельного desktop-клиента нет.

## Что лежит в каталоге

- `itms-stack.service` — поднимает `docker compose up -d` из `/opt/itms/deploy` при старте системы
- `first-boot.sh` — если нет `/opt/itms/deploy/.env`, копирует пример и подставляет случайные пароли, затем запускает стек и печатает адрес
- `autoinstall/user-data` — черновик Subiquity для Ubuntu Server 24.04: Docker, каталог `/opt/itms`, включение unit

## Как этим пользоваться

1. Поставить Ubuntu Server 24.04 и Docker Engine с плагином Compose.
2. Скопировать репозиторий в `/opt/itms`.
3. Запустить `sudo bash /opt/itms/appliance/first-boot.sh`.
4. Открыть адрес, который скрипт напечатал. Пароль владельца — в `/root/itms-first-boot.txt` на этой машине, не в git.

Обновление уже установленной системы — `docker compose pull && docker compose up -d` в `/opt/itms/deploy`. Новый ISO для этого не нужен.

## Резервная копия

`pg_dump` из контейнера Postgres по расписанию systemd-timer. Восстановление — `psql` в тот же контейнер. Секреты остаются только в `/opt/itms/deploy/.env`.

## Сборка ISO позже

`live-build`: хуки ставят Docker, копируют `itms/deploy` и этот каталог, включают `itms-stack.service`. Проверка — загрузка в QEMU до ответа `/health`. Подпись SHA256. Этот шаг не выполнен.
