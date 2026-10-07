---
name: mail
description: Почта Яндекса и Gmail через MCP — папки, письма, перенос и удаление.
version: 1.2.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [email, mail, mcp]
    category: productivity
    related_skills: [desk, calendar]
---

# Почта

Ящики Яндекса и Gmail — серверы MCP `yandex` и `gmail`. Пароль не проси и IMAP сам не поднимай.

Инструменты, которые нужно вызвать, а не описать словами:

- `yandex_status` / `gmail_status` — ящик отвечает или нет
- `yandex_folders` / `gmail_folders` — какие папки уже есть
- `yandex_recent` / `gmail_recent` — последние письма, у каждого есть uid
- `yandex_frequent_senders` / `gmail_frequent_senders` — кто пишет чаще, по подсчёту
- `yandex_create_folder` / `gmail_create_folder` — одна папка
- `yandex_create_sender_folders` / `gmail_create_sender_folders` — папки для повторяющихся отправителей
- `yandex_move` / `gmail_move` — перенести письма по uid в существующую папку
- `yandex_delete` / `gmail_delete` — удалить письма по uid

`create_sender_folders` создаёт только те папки, которые следуют из выборки. Письма он не перекладывает и не удаляет. Перенос и удаление делай отдельными инструментами и только когда владелец явно попросил именно это. Сначала `recent`: uid бери из ответа, не угадывай. За раз не больше 20 писем и только те, которые он назвал. Если ящик не настроен, так и скажи — не предлагай режим Agent и не говори, что почта только для чтения.

Отправку письма не делай, пока владелец явно не скажет «отправь».
