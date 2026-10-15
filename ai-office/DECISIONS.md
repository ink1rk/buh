# DECISIONS

- ADR 0001: отдельная VM 115, без изменений существующих гостей и reverse proxy.
- ADR 0002: single-node k3s, встроенный datastore, без публичного ingress.
- Gateway MVP: long polling. Webhook не поднимается одновременно.
- Внешняя запись календаря и почты только после одноразового approval.
- Образ Job с placeholder digest кластер не принимает.
- OAuth refresh token без префикса `enc:v1:` не записывается.
- Файлы проверенного образа Ubuntu удалены после импорта диска VM 115. Чужие образы на `local` оставлены.
- Пароль cloud-init убран из конфига VM. Задание бэкапа гостей 100–103 не дополнено диском 512 GiB: на `local` нет места.
