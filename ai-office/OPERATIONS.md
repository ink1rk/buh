# OPERATIONS

## Доступ

Администратор гостя: `aioffice`. SSH принимает только ключ. В `/etc/ssh/sshd_config.d/99-aioffice.conf` выключены `PasswordAuthentication`, `KbdInteractiveAuthentication` и `PermitRootLogin`.

Первый закрытый ключ лежит на госте: `/home/aioffice/bootstrap-key`, режим `600`, владелец `aioffice`. Его нужно скопировать к себе и удалить с диска VM. Отпечаток: `SHA256:Ek2Jx+GfhQ4/o+QedtihKawsC4OoQ+AnN6VGbVpJPhU`.

Пароль консоли в git не хранится. В конфиге Proxmox поле `cipassword` отсутствует. `qemu-guest-agent` в состоянии active, ping через API ответил.

Kubernetes API наружу не пробрасывается. Kubeconfig k3s создан с режимом `600`. В репозиторий его не копировать.

## k3s

Версия: `v1.36.5+k3s1`. SHA-256 `/usr/local/bin/k3s`: `d73847bcd3c5fccef0115b372e2f9a91f3032dc84bbf71518a4617565294d313`.

Параметры сервера: `--write-kubeconfig-mode 600 --disable traefik --disable servicelb` плюс адрес этого узла в `--node-ip` и `--tls-san`.

Остановка: `systemctl stop k3s`. Запуск: `systemctl start k3s`. Обновление только на явно выбранную версию, не `latest`. Второй узел к встроенному datastore не добавлять.

Firewall гостя: по умолчанию входящие запрещены. Снаружи открыт только SSH из сети моста. Сети подов и сервисов k3s разрешены внутри гостя. Правила датацентра Proxmox не менялись.

## Бэкап

Отдельного backup storage нет. Задание, которое копирует media, proxy, ausra и wg-hub, не расширялось на VM 115: каталог `local` не вмещает диск 512 GiB.

Когда появится PostgreSQL и место для дампа:

```bash
pg_dump --format=custom --file=ai-office.dump "$DATABASE_URL"
```

Восстановление проверять на отдельной базе, не поверх рабочей. Откат VM описан в `docs/runbooks/rollback.md`.
