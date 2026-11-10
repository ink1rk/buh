# R11 Data Lineage

Путь одного инфоповода:

1. `SourceItem` (`available_at`, `lab_run_id`, cassette/origin_mode)
2. `Story` + `StoryCluster` (ключ CVE/repo/url)
3. `StoryDossier` + `EditorialClaim` (URL не повышает статус до independently_verified)
4. `EditorialBrief`
5. `Post` + `EditorialVariant` (2–3 угла, bound to cluster story, без last-post fallback)
6. `MediaAsset` (JPEG studio-v3, `fits` обязателен)
7. `Episode` (`proposed` / vacancy task)
8. `WorkflowRun` / `WorkflowStep` (`output_ref` на каждый шаг)
9. Человек: `approval_requested` → `approved_or_rejected`
10. `ready_for_delivery` всегда false при текущих флагах. Telegram transport = None.

Лаборатория сериализует дневные агрегаты в `lab_daily_snapshots`. День N не видит события с `available_at` позже конца дня N.
