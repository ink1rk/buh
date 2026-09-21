# Личный ассистент («Джарвис»)

Код сервисов ассистента, который живёт на VM в `/opt/assistant`. Этот каталог —
версионируемая копия: правим здесь, копируем на хост, перезапускаем systemd.

## Состав

| Файл | Что делает |
| --- | --- |
| `assistant.py` | ядро, FastAPI на `:8800`: промпт, роутер мозга, память, погода, финансы, брифинг, голос |
| `news.py` | сбор и компоновка новостей: 8 лент, дедупликация, темы, рендер в HTML/текст/голос |
| `tgfmt.py` | приведение ответов модели к Telegram-HTML (и обратно — в чистый текст для TTS) |
| `tg_bot.py` | Telegram-канал: команды, inline-кнопки, голосовые, расписание брифингов |
| `tests/test_format.py` | офлайн-тесты компоновки новостей и форматтера |

Рядом на хосте: `tg_user_service.py` (личный аккаунт через Telethon, `:8810`),
`cursor-gateway` (`:8791`), `ollama` (`:11434`), приложение финансов (`nginx :80`).

## Как новости собираются

1. **Сбор.** Ленты тянутся параллельно; для каждого хоста запоминается рабочий
   маршрут (напрямую или через прокси пользователя), поэтому повторные обходы
   быстрые. Ленты и их темы настраиваются через `NEWS_FEEDS`
   (`Название|url` или `Название|url|тема`).
2. **Фильтр шума.** Выбрасываются рубрики вроде «Из жизни»/«Стиль» и заголовки
   в духе «показала фигуру», «гороскоп», «на правах рекламы»
   (`NEWS_SKIP_CATEGORIES`, `NEWS_JUNK_EXTRA`).
3. **Дедупликация.** Похожие заголовки из разных изданий склеиваются в одну
   новость со списком источников — такие новости помечаются 🔸 и поднимаются в
   «Главное».
4. **Темы.** Сначала рубрика RSS, потом путь ссылки, потом ключевые слова по
   заголовку (сводка используется только как подсказка).
5. **Ранжирование.** Больше источников и весомые формулировки — выше;
   «Названы…», «Раскрыл…» и прочий клик-бейт опускается.
6. **Компоновка.** Блок «Главное» + разделы по темам, не больше N на тему и с
   ограничением на одно издание, чтобы лента не превращалась в один ТАСС.
7. **Рендер.** `render_html` (Telegram: заголовок-ссылка + источники + свежесть),
   `render_flat` (плоский топ для брифинга), `render_text`, `render_voice`,
   `context` (для промпта) и `digest_prompt` (сводка «своими словами»).

Кэш держится тёплым фоновым потоком (`NEWS_CACHE_TTL`, по умолчанию 5 минут),
поэтому `/news` отвечает за миллисекунды, а не за 10 секунд.

## API ядра

```
GET  /health                      статус мозгов + статистика новостей
POST /chat                        {text, session, brain, channel}
GET  /news?limit=&topic=&force=   сгруппированные новости: html/text/voice/items
GET  /news/digest?brain=          сводка новостей, собранная моделью
GET  /briefing?evening=&raw=      сводка дня: текст + голосовой вариант
GET  /weather                     строка погоды + сырые данные
POST /stt  /tts  /voice           голос
```

## Промпт

`build_system(channel, blocks, facts, brain)` собирает системный промпт из частей:
персона → принципы (что делать с данными, когда спрашивать, что подтверждать) →
формат под канал (Telegram-HTML или голос; для локальной 7B-модели формат короче,
она хуже держит длинные инструкции) → список умений → текущие дата/время/город →
факты о пользователе → блок ДАННЫЕ → короткое напоминание в конце.

Роутер: приватные интенты (финансы, переписки) уходят в локальную Ollama,
новости и «подумать» — в Cursor-шлюз, остальное — локально. Если один мозг
недоступен, ответ добирается вторым.

## Деплой

```bash
# с машины разработки
scp assistant/{assistant,news,tgfmt,tg_bot}.py user@host:/tmp/
ssh user@host '
  TS=$(date +%Y%m%d-%H%M%S)
  sudo mkdir -p /opt/assistant/backups/$TS
  sudo cp /opt/assistant/{assistant,tg_bot}.py /opt/assistant/backups/$TS/
  for f in news.py tgfmt.py assistant.py tg_bot.py; do
    sudo install -o root -g root -m 755 /tmp/$f /opt/assistant/$f
  done
  sudo /opt/assistant/.venv/bin/python -m py_compile /opt/assistant/*.py
  sudo systemctl restart assistant && sleep 8 && curl -s localhost:8800/health
  sudo systemctl restart assistant-telegram
'
```

Тесты: `/opt/assistant/.venv/bin/python -m pytest /opt/assistant/tests -q`
(сети не требуют). Логи: `journalctl -u assistant -f`,
`journalctl -u assistant-telegram -f`.

## Переменные окружения

Секреты лежат только в `/etc/assistant.env` и `/etc/assistant-telegram.env`
(права 600) и в репозиторий не попадают.

Ядро: `OLLAMA_URL`, `OLLAMA_MODEL`, `GATEWAY_URL`, `GATEWAY_KEY`, `GATEWAY_MODEL`,
`FINANCE_API`, `TG_USER_URL`, `ASSISTANT_DB`, `WHISPER_MODEL`, `PIPER_VOICE`,
`EXT_PROXY`, `WEATHER_LAT`, `WEATHER_LON`, `WEATHER_PLACE`, `TZ_NAME`,
`NEWS_FEEDS`, `NEWS_CACHE_TTL`, `NEWS_SKIP_CATEGORIES`, `NEWS_JUNK_EXTRA`,
`NEWS_DIRECT_TIMEOUT`, `NEWS_PROXY_TIMEOUT`.

Бот: `TG_TOKEN`, `TG_ALLOWED_ID`, `ASSISTANT_URL`, `TG_USER_URL`, `TG_PROXY`,
`TZ_NAME`, `BRIEFING_TIME`, `EVENING_BRIEFING_TIME` (пусто — вечерний брифинг
только по команде `/evening`), `TG_NEWS_LIMIT`.
