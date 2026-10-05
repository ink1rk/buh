---
name: finance
description: Разбор денег по выписке — доход, траты, остаток, крупные места и совет с цифрами.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [finance, budget]
    category: productivity
    related_skills: [desk, obsidian]
    requires_toolsets: [terminal]
---

# Финансы

```bash
PYTHONPATH=. python3 -m desk finance
```

Бери `headline`, `advice`, `categories`, `counterparties`. Это средние по полным месяцам, не обрывок текущего месяца.

Переводы себе — не трата на жизнь. Если совет говорит, что они забирают остаток, так и передай.

Записать вывод в vault, если владелец просит запомнить:

```bash
PYTHONPATH=. python3 -m desk note "Деньги" "краткий вывод" "02 Finance"
```

Новую операцию и новую выписку не создавай из воздуха. Загрузка выписки — в финансовом приложении или через его MCP, когда владелец дал файл.
