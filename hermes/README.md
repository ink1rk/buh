# Hermes

Разговор, навыки и голос — [Hermes Agent](https://hermes-agent.nousresearch.com). Почта и календарь остаются сервисом ассистента на этой машине. Память — vault Obsidian в `vault/`.

## Модули

| Навык | Что делает |
|---|---|
| `desk` | какой модуль звать |
| `mail` | ящики Яндекса и Gmail |
| `calendar` | встречи |
| `obsidian` | записать и найти заметку |
| `browser` | страница в браузере Hermes |
| `telegram` | бот владельца, без сбора чужих чатов |
| `voice` | ElevenLabs |

Команды читает `python3 -m desk` из этого каталога.

## Поставить

На Ubuntu от root:

```sh
BRANCH=cursor/news-composition-and-prompt-d806 bash hermes/deploy-host.sh
```

Скрипт клонирует репозиторий в `/opt/assistant`, поднимает ассистента на `127.0.0.1:8800` и ставит Hermes пользователю `cursor`. Чужие чаты Telegram не собираются. Ключи модели, ElevenLabs и бота дописываются в `/home/cursor/.hermes/.env`, затем `hermes model` и `hermes gateway setup`.

Бинарник Hermes — по инструкции Nous Research. Профиль:

```sh
HERMES_HOME=~/.hermes sh hermes/install.sh
```

Секреты в `$HERMES_HOME/.env`: ключ модели, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `TELEGRAM_BOT_TOKEN`. Образец — `env.example`.

В Telegram голос: `/voice tts`. Чужие личные чаты не включаем.
