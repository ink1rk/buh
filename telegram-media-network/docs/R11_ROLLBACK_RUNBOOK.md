# R11 Rollback Runbook

1. Не вызывайте `alembic downgrade`. `0007_r11_editorial_pilot` поднимает `RuntimeError`: откат удалил бы lineage, дневные снимки лаборатории и журнал LLM.
2. Forward-fix: оставить `0007` и чистить строки явно через `purge_lab(lab_run_id)`.
3. R9 DEMO (`_load`) не трогается, если чистить только `lab_run_id` лаборатории.
4. Восстановление: `scripts/r11_backup_restore.py` поднимает dump в изолированную базу `tmn_r11_restore` и проверяет `SCHEMA_HEAD`.
5. UI и API остаются fail-closed: `DRY_RUN=true`, `PUBLISH_ENABLED=false`, `GLOBAL_KILL_SWITCH=true`.
6. Если лаборатория зависла на дне N, повторный `load_lab(through_day=30)` продолжает с `current_day+1` и не импортирует дни, для которых уже есть `lab_daily_snapshots`.
