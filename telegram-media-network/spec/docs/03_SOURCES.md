# 03. Реестр источников и стратегия получения данных

## 3.1 Verified official references (проверено 10.11.2026)

| Источник | API/Feed | Сфера | Исходный polling | Оговорка |
|---|---|---|---|---|
| GitHub REST | https://docs.github.com/en/rest/search/search | Github, DevPulse, AI tools, Infra, HomeLab | каждые 30 мин для групп запросов | Основной REST без auth 60/h, с auth обычно 5000/h; search отдельные лимиты. Учитывать headers/secondary limits. |
| GitHub Releases | https://docs.github.com/en/rest/releases/releases | версионные релизы | 1–2 часа | Нужна whitelist-repo подписка; версия != дата создания проекта |
| Hugging Face Hub | https://huggingface.co/docs/hub/en/api | AI/AI tools | 60 минут | Hub tier лимиты плавающие, `huggingface_hub`, без скачивания весов |
| Hacker News API | https://github.com/HackerNews/API | Tech, Dev, AI | 20 минут | `topstories/newstories/showstories` и `/item/{id}.json`, не считать всё голосованием за качество |
| arXiv RSS | https://github.com/arXiv/arxiv-docs/blob/develop/source/help/rss.md | AI, science | 1 раз/сутки + окно | `https://rss.arxiv.org/rss/cs.AI`, `cs.LG`, `cs.RO`; статьи могут быть preprint |
| CISA KEV | https://github.com/cisagov/kev-data | Cyber | 60 минут | Только новые `cveID`/изменения записи, предупреждение об актуальной эксплуатации из KEV |
| Cloudflare Changelog RSS | https://developers.cloudflare.com/fundamentals/new-features/consuming-rss-feeds/ | Infra/Dev | 2 часа | RSS официальных changelogs |
| Kubernetes blog | https://kubernetes.io/feed.xml | Infra | 2 часа | Проверить статус feed и content licensing |
| PyPI RSS | https://pypi.org/rss/updates.xml | Dev | 3 часа | Очень шумный: только отслеживаемые пакеты/релизы |

Не считать любую ссылку из таблицы гарантией постоянной доступности. Перед включением source выполнить smoke test: DNS, HTTP 200/304, content type, robots/ToS, валидные даты, лицензия метаданных и cooldown.

## 3.2 GitHub discovery — точный алгоритм

Сделать отдельные категории запросов, например:

- `topic:self-hosted pushed:>=<UTC-30d> archived:false` → HomeLab;
- `topic:llm created:>=<UTC-30d> archived:false` → AI Tools;
- `topic:devtools created:>=<UTC-30d> archived:false` → DevPulse;
- `topic:security-tool pushed:>=<UTC-30d> archived:false` → Cyber tools (не автоматически одобрять);
- `topic:docker pushed:>=<UTC-30d> archived:false` → Infra/HomeLab;

Это примеры конструирования запросов, а **не статические URLs**. Проверить grammar через GitHub docs. Для каждого запроса: максимальное число страниц/результатов, сортировка `updated` или `stars`, кеширование, независимый state cursor, `X-RateLimit-*`, 403/429 exponential backoff. Снимать снапшот stars/forks/last pushed для тренда и вычислять `stars_delta_7d`, а не верить одному счётчику. Не ранжировать только по звёздам; отвергать forks/archived/неактивные без отдельной пользы. Наличие `license.spdx_id` проверять для заявлений «open-source»: если неизвестно — сказать «публичный репозиторий», не «бесплатный OSS с правом свободного использования». Не скачивать и не выполнять чужие скрипты и release binaries.

Для экосистемы GitHub не использовать неофициальный Trending scrape как обязательную зависимость. Можно брать официальные Search API и события релизов, источники поддерживать как адаптеры.

## 3.3 Научные публикации

Не делать из arXiv формулировки «учёные доказали» только из abstract. Сохранять arxiv id, авторов, версии, время публикации, принадлежность категории и статус preprint. Если нет второго независимого источника и результат сенсационный, отправлять на человека либо отклонять.

## 3.4 Уязвимости

CISA KEV гарантирует только факт включения конкретной уязвимости в каталог известных эксплуатируемых. Не утверждать, что любая CVE «эксплуатируется», если её там нет. CVSS из NVD (если подключён отдельным адаптером) и KEV-факт **разные признаки**. В предупреждениях: CVE, вендор, затронутый продукт, дата записи, краткая защитная рекомендация из первоисточника, ссылка. Запрет на автоматическую публикацию эксплуатационных PoC, инструкций атаки, вредоносных payload и неподтверждённых деталей. Emergency critical alert только manual 2nd review.

## 3.5 Протокол source adapter

```python
class SourceAdapter(Protocol):
    source_id: str
    async def discover(self, since: datetime | None, limit: int) -> list[SourceItem]: ...
    async def validate_source(self) -> SourceHealth: ...
```

Хранить `last_success`, `last_run`, `last_error`, `etag`, `last_modified`, `next_retry`, источник URL/TOS и среднюю latency. Метрики `source_success_total`, `source_http_status_total`, `new_items_total`, `source_backoff_seconds`. Сеть без авторизации к бесплатным endpoints где допустимо; GitHub token публичного read-only scope только если нужен. HF token — только публичный read access.

## 3.6 Источник → канал

| Source | AI news | AI tools | Github | Cyber | Infra | HomeLab | Dev | Future |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GitHub repos/releases | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Hugging Face | ✓ | ✓ | — | — | — | ✓ | ✓ | ✓ |
| HN | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| arXiv | ✓ | — | — | — | — | — | ✓ | ✓ |
| CISA KEV | — | — | — | ✓ | ✓* | — | — | — |
| Cloudflare/K8s | — | — | — | ✓* | ✓ | ✓ | ✓ | — |
| PyPI | — | ✓ | ✓ | ✓* | ✓ | ✓ | ✓ | — |

`✓*` — вторичная тематическая связка, не повод создавать два одинаковых поста.

## 3.7 Ссылки и правовые оговорки

- GitHub лицензирование: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository — публичный репозиторий без лицензии **не является свободным для копирования**.
- Hugging Face quotas: https://huggingface.co/docs/hub/en/rate-limits — следовать текущим заголовкам квот, а не жестко закодированным цифрам.
- arXiv feeds: https://github.com/arXiv/arxiv-docs/blob/develop/source/help/rss.md — учесть условия API.
- Telegram publisher: https://core.telegram.org/bots/api — уточнить версии формата/лимиты перед staging.

Любой новый источник добавлять только после индивидуальной проверки источника, robots/ToS, частоты и данных для корректного attribution.
