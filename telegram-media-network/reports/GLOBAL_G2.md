# G2. Редакция

Метка: UNIT TESTED. Модель не вызывалась. Невалидный JSON не создаёт outbox.

`materialise_desk` пишет 24 synthetic-поста, по три на канал, статус `NEEDS_REVIEW`. У каждого три `PostVersion` и снимки доказательств с `verified_at = None`. Cyber требует два подтверждения. Текст cyber говорит «не сводка по всем установкам» и не содержит CVSS. Угол future прямо пишет, что препринт не равен рецензии. Угол github говорит, что лицензия не подтверждена, и не называет MIT.

`fallback_from_invalid` возвращает черновик с `requires_review` и не ставит публикацию. `test_g2_drafts_are_checkable_and_not_published`.

В редакторе фраза, источник и пометка «проверено: нет» видны на `/review/{id}`. Скриншоты: `reports/screenshots/global/editor-1280.png`, `editor-375.png`.

Ограничение: факты извлечены из учебного текста. Они не проверены человеком и не являются новостью.
