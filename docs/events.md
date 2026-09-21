# События

Шина — `core/events.py`. Внутрипроцессная, потокобезопасная, с двумя режимами
доставки: `publish` (синхронно, в потоке издателя) и `publish_async` (в фоне,
для горячего пути). Публичный интерфейс не зависит от транспорта, поэтому
замена на Redis/NATS позже не затронет бизнес-логику.

## Формат

```json
{
  "id": "evt-8f1c…",
  "type": "telegram.message.received",
  "source": "telegram",
  "payload": {"peer_id": "900001", "text": "…"},
  "correlation_id": "corr-1a2b…",
  "causation_id": "evt-4d5e…",
  "ts": 1790019667.12
}
```

`correlation_id` живёт всю цепочку, `causation_id` указывает на событие-причину
(`Event.child()` создаёт производное событие с обоими полями).

## Подписка

```python
bus.subscribe("telegram.message.received", handler)   # точный тип
bus.subscribe("memory.*", handler)                    # префикс
bus.subscribe("*", handler)                           # всё (так работает аудит)
bus.unsubscribe(handler)
```

Исключение в обработчике логируется и не мешает остальным подписчикам и
издателю.

## Хранение

Все события пишутся в таблицу `events`. Retention — `EVENT_RETENTION_DAYS`
(по умолчанию 30 дней), старые удаляются при миграции на старте.

## Каталог типов

### Сообщения
| Тип | Когда |
|---|---|
| `message.received` | любое входящее сообщение (в том числе от владельца) |
| `message.transcribed` | голосовое распознано |
| `telegram.message.received` | человек написал владельцу |
| `telegram.message.sent` | ответ отправлен от имени владельца |

### Пайплайн
| Тип | Когда |
|---|---|
| `intent.detected` | намерения определены |
| `response.generated` | агент сформировал ответ |

### Действия
| Тип | Когда |
|---|---|
| `action.requested` | действие создано и провалидировано |
| `action.approval.required` | требуется подтверждение владельца |
| `action.approved` | владелец подтвердил |
| `action.denied` | запрещено политикой |
| `action.cancelled` | отменено |
| `action.executed` | выполнено успешно |
| `action.failed` | провайдер вернул ошибку |
| `action.expired` | подтверждение просрочено |

### Уведомления
| Тип | Когда |
|---|---|
| `notification.created` | уведомление создано (с решением политики) |
| `notification.sent` | канал доставил его владельцу |
| `notification.suppressed` | политика решила не беспокоить |

### Память и люди
| Тип | Когда |
|---|---|
| `memory.candidate.detected` | кандидат в память найден (с исходом обработки) |
| `memory.created` / `memory.updated` | запись создана / усилена |
| `memory.superseded` | новая информация заменила старую |
| `memory.deleted` | запись удалена физически |
| `contact.created` / `contact.updated` | контакт появился / изменился |
| `contact.resolved` | имя сопоставлено с контактом |
| `conversation.created` / `conversation.updated` | диалог создан / получил summary |
| `episode.created` / `episode.updated` | эпизод открыт / дополнен |
| `commitment.created` / `commitment.completed` / `commitment.overdue` | обязательства |
| `reply.suggestion.created` | подготовлены варианты ответа |
| `task.candidate.detected` | в сообщении просьба-напоминание (задача, не память) |

### Система
| Тип | Когда |
|---|---|
| `integration.status.changed` | интеграция сменила статус |
| `system.alert` | внутренняя проблема, требующая внимания |
