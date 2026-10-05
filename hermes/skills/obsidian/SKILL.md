---
name: obsidian
description: Память в Obsidian — записать заметку во входящие и найти по vault.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [obsidian, notes, memory]
    category: note-taking
    related_skills: [desk]
    requires_toolsets: [terminal]
---

# Obsidian

Vault — источник памяти. Путь в `OBSIDIAN_VAULT_PATH`. Не пиши заметки мимо него.

Папки:

- `00 Inbox` — всё новое
- `01 Daily` — день
- `02 Finance` — выводы по деньгам
- `03 People` — люди

Записать:

```bash
PYTHONPATH=. python3 -m desk note "Заголовок" "текст" "00 Inbox"
```

Найти:

```bash
PYTHONPATH=. python3 -m desk search "фраза"
```

Перед ответом «я этого не помню» сначала поиск. В заметку клади факт, который владелец просил сохранить, без пересказа всей переписки.
