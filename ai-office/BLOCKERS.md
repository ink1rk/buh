# Открытые решения и работы

Требует владельца:

1. Часовой пояс: задаётся самим владельцем в боте `/timezone Europe/Moscow` либо другая IANA-зона. Сейчас пустой.
2. Первый календарь: Google/Microsoft с OAuth или Яндекс с отдельным CalDAV adapter. Выбор пока не получен; выданные пароли сами по себе не означают выбор сервиса.
3. Постоянная независимая копия VM/БД. На PVE local доступно около 16.4 GiB, local-lvm — images/rootdir, не backup content. Ежедневные дампы в VM не покрывают потерю её диска. Ручная копия на компьютер проверена.
4. Сверка фактических расходов Cursor: get_usage для аккаунта недоступен. Выбор провайдера/модели уже подтверждён; повторно ключ для него не требуется.

Технический backlog:

- LiteLLM с PostgreSQL/virtual keys либо отдельно утверждённый отказ от этого требования для Cursor SDK пути.
- Trusted job-launcher, настоящий researcher, loop/failure/recovery tests.
- Календарный read-only adapter, approval UI, idempotent calendar writes, OAuth encryption.
- Живые T01–T15, полное восстановление VM, проверка после reboot, мониторинг/сигнализация, подписи образов.
- Files/voice ingress, полноценные export/delete, миграционный downgrade/runbooks следующих версий.

