# G5. Программы

Метка: UNIT TESTED. Ни один выпуск не получает статус published.

Пять серий: `ai_daily`, `tool_day`, `cve_review`, `selfhosted_week`, `science_week`. `propose_fortnight` начинает со следующего дня Europe/Moscow и идёт 14 дней. Недельные серии только по понедельникам. Тихий слот пропускается. Занятый слот пишется в conflicts и не затирается. Если кластеров меньше минимума, пост не выдумывается: на пустой базе `created == 0` и причина `not_enough_material`.

После учебного пакета выпуски есть, все `proposed`, опубликованных постов нет. Повторный проход не создаёт вторую пачку поверх занятых слотов. `test_g5_calendar_does_not_invent_or_publish`, `test_g5_thin_series_stays_empty`.

Ограничение: слоты — предложения редакции. Они не стоят в outbox и не уходят в Telegram.
