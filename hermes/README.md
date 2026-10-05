# Hermes

Разговор, навыки и голос — [Hermes Agent](https://hermes-agent.nousresearch.com). Почта, календарь и финансы остаются сервисами на этой машине. Память — vault Obsidian в `vault/`.

## Модули

| Навык | Что делает |
|---|---|
| `desk` | какой модуль звать |
| `mail` | ящики Яндекса и Gmail |
| `calendar` | встречи и платежи |
| `finance` | разбор выписки |
| `obsidian` | записать и найти заметку |
| `browser` | страница в браузере Hermes |
| `telegram` | бот владельца, без сбора чужих чатов |
| `voice` | ElevenLabs |

Команды читает `python3 -m desk` из этого каталога.

## Поставить

Бинарник Hermes — по инструкции Nous Research (`hermes model`, затем `hermes gateway setup` для Telegram). Профиль:

```sh
HERMES_HOME=~/.hermes sh hermes/install.sh
```

Секреты в `$HERMES_HOME/.env`: ключ модели, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `TELEGRAM_BOT_TOKEN`, `MCP_TOKEN`. Образец — `env.example`.

В Telegram голос: `/voice tts`. Чужие личные чаты не включаем.
