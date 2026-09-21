# Действия

Любое действие во внешнем мире проходит через Action Engine
(`core/actions.py`). Прямых вызовов внешних API из агентов и интерфейсов нет.

## Конвейер

```
REQUEST → VALIDATE → PERMISSION CHECK → (WAIT APPROVAL) → EXECUTE
        → STORE RESULT → PUBLISH EVENT
```

1. **REQUEST** — `engine.request(type, parameters, …)`. Если передан
   `idempotency_key` и действие с таким ключом уже есть, возвращается прежнее:
   повтор не создаёт второй отправки.
2. **VALIDATE** — `provider.validate(action)`. Ошибка валидации терминальна,
   ретраев нет.
3. **PERMISSION CHECK** — движок разрешений возвращает `ALLOW`, `DENY` или
   `REQUIRE_APPROVAL`. Сам Action Engine ничего не решает.
4. **WAIT APPROVAL** — статус `WAITING_APPROVAL`, срок жизни
   `ACTION_APPROVAL_TTL` (по умолчанию 10 минут), владельцу уходит уведомление
   с кнопками. Просроченное подтверждение не выполняется никогда.
5. **EXECUTE** — `provider.execute(action)` с ограниченными ретраями.
6. **STORE / PUBLISH** — результат и ошибка сохраняются, событие публикуется.

## Модель

```json
{
  "id": "act-fac52e65a0124758",
  "type": "send.telegram.message",
  "source": "telegram",
  "parameters": {"chat_id": 1630534981, "text": "…"},
  "risk_level": "MEDIUM",
  "status": "SUCCESS",
  "requires_confirmation": true,
  "requested_by": "user:owner",
  "idempotency_key": "reply:sug-…:0",
  "correlation_id": "corr-…",
  "created_at": 1790019667.1,
  "approved_at": 1790019675.4,
  "executed_at": 1790019675.9,
  "attempts": 1,
  "result": {"transport": "bot", "message_id": 51},
  "error": null
}
```

Статусы: `PENDING`, `WAITING_APPROVAL`, `APPROVED`, `RUNNING`, `SUCCESS`,
`FAILED`, `CANCELLED`, `EXPIRED`.

## Провайдеры

```python
class ActionProvider:
    action_types = ("send.telegram.message",)
    def supports(self, action_type): ...
    def validate(self, action): ...
    def execute(self, action): ...
```

| Провайдер | Типы действий | Статус |
|---|---|---|
| `providers/telegram.py` | `send.telegram.message`, `edit.telegram.message`, `delete.telegram.message` | реализовано |

Провайдер сам выбирает транспорт: `as_user` или наличие только `peer_id` →
отправка через аккаунт владельца (`tg-user`); `chat_id` → отправка ботом.

Зарезервированные типы, для которых провайдеров пока нет (действие честно
завершится `FAILED` с текстом «нет провайдера»): `send.email`,
`create.calendar.event`, `create.task`, `call.taxi`, `purchase.ozon`,
`bank.transfer`.

## Идемпотентность

Ключ обязателен там, где повтор стоит дорого:

* отправка выбранного варианта ответа — `reply:<suggestion_id>:<index>`;
* в будущем: покупки, такси, платежи — `action id + operation id` провайдера.

Уникальный индекс в таблице `actions` делает защиту устойчивой к перезапуску
процесса, а не только к повтору в памяти.

## Ретраи

Повторяются только те ошибки, которые имеют смысл повторять:

| Ошибка | Ретрай |
|---|---|
| таймаут, обрыв соединения, HTTP 5xx, HTTP 429 | да |
| неверные учётные данные, запрет, валидация | нет |
| `ProviderError(retryable=False)` | нет |

Параметры: `ACTION_MAX_ATTEMPTS` (3), `ACTION_RETRY_BACKOFF` (2.0 —
экспоненциально).

## Ошибки интеграций

Недоступный внешний сервис не ломает ядро: действие получает `FAILED`, в
журнал попадает причина, владельцу уходит уведомление «не удалось отправить»,
остальная система продолжает работать.

## API

```
POST   /api/actions                  создать заявку
GET    /api/actions?status=…         список
GET    /api/actions/{id}             одно действие
POST   /api/actions/{id}/approve     подтвердить и выполнить
POST   /api/actions/{id}/cancel      отменить
```
