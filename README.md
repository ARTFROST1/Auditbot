# Auditbot

Telegram-бот воронки для привлечения клиентов на платный аудит Яндекс.Директа.

## Архитектура

```
Auditbot/
├── bot.py           # Точка входа, FSM-хендлеры, обработчики напоминаний
├── scheduler.py     # Персистентный планировщик (сохраняет таймеры в reminders.json)
├── config.py        # Переменные окружения из .env
├── logger.py        # Логирование (консоль + файл)
├── messages.py      # Тексты сообщений, inline-клавиатуры, callback-константы
├── metrika.py       # Сервис оффлайн-конверсий Яндекс.Метрики
├── bot_schema.md    # Схема логики бота (wireframes)
├── pyproject.toml   # Зависимости (UV)
├── .env.example     # Шаблон переменных окружения
├── reminders.json   # Авто-создаётся: сохранённые отложенные напоминания
└── logs.log         # Лог-файл (создаётся автоматически)
```

## Воронка

```
/start ─→ Приветствие ─[5 сек]─→ Вопрос 1 (реклама работала?)
                                    │
                           Да ──────┼────── Нет
                           │                │
                      Бюджет >50k     Бюджет >100k
                        │    │          │    │
                       Да   Нет        Да   Нет
                        │    │          │    │
                        └────┼──────────┘    │
                             │               │
                       Ключевая цель     Отказ → Заявка
                        │          │
                   Текст      [10 мин]
                    │         Напоминание
                    │              │
              Запрос доступа ──────┘
                    │
              [10 мин] → Напоминание
                    │
              Стоимость (10 000 ₽)
               │            │
           По счёту    Другой способ
               │            │
          Заявка +     Индивидуальный
          реквизиты    формат → Заявка
```

На каждом этапе неактивности (10 мин / 24 ч) бот отправляет напоминание.
Если пользователь не реагирует 24 ч после напоминания — финальная заглушка.

## Яндекс.Метрика

Бот отправляет **оффлайн-конверсии** в двух точках:

| Событие | Когда | Переменная |
|---------|-------|------------|
| Бот запущен | `/start` | `GOAL_BOT_STARTED` |
| Заявка получена | Сообщения 13/14 | `GOAL_LEAD_RECEIVED` |

### ClientId (deep-link)

Для корректной привязки конверсии к визиту Метрики пользователь должен
запустить бота через deep-link с передачей `_ym_uid`:

```
https://t.me/your_bot?start=cid_1234567890
```

Где `1234567890` — значение cookie `_ym_uid` пользователя.
Если ClientId не передан, используется Telegram user ID как fallback.

## Персистентный планировщик (`scheduler.py`)

### Проблема (до исправления)

Все таймеры хранились в `asyncio.Task` в RAM. При любом перезапуске
сервиса (`systemd Restart=always`) задачи `asyncio` безвозвратно терялись.
24-часовые напоминания в такой архитектуре **никогда не доходили** до
пользователя — сервис перезапускается гораздо чаще, чем раз в сутки
(обновления, падения, плановый рестарт).

Дополнительно, вложенные вызовы `_schedule_timeout` из внутри уже
запущенного callback вызывали `task.cancel()` на саму текущую задачу,
что уничтожало следующее финальное напоминание (оно удалялось из
словаря `_timeout_tasks` блоком `finally`).

### Решение

`scheduler.py` сохраняет каждое напланированное напоминание в
`reminders.json` и при рестарте восстанавливает незавершённые задачи:

```
scheduler.schedule(user_id, "price_reminder", 86400, expected_state=...)
    → пишет в reminders.json
    → создаёт asyncio.Task

# Если бот упал и поднялся снова:
await scheduler.restore_on_startup()
    → читает reminders.json
    → для каждой записи восстанавливает FSM-состояние пользователя
    → пересоздаёт asyncio.Task с оставшимся временем
```

Поддерживаемые типы напоминаний:

| Тип | Когда | Действие |
|-----|-------|---------|
| `goal_reminder` | 10 мин без ответа о цели | Отправляет напоминание, ставит `goal_reminder` |
| `goal_final` | +24ч без реакции | Финальное сообщение, `finished` |
| `access_reminder` | 10 мин без доступа | Напоминание о доступе, `access_reminder` |
| `access_final` | +24ч без реакции | Финальное сообщение, `finished` |
| `price_reminder` | 24ч без ответа на цену | Напоминание о цене, `price_reminder` |
| `price_final` | +24ч без реакции | Финальное сообщение, `finished` |

**Примечание:** Приветственный 5-секундный таймер `GREETING_DELAY` не
персистируется (потеря некритична — пользователь нажмёт кнопку сам).

---

## Установка и запуск

```bash
cd Auditbot

# Скопировать и заполнить .env
cp .env.example .env

# Установить зависимости
uv sync

# Запуск
uv run bot.py
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен Telegram-бота от @BotFather |
| `ADMIN_CHAT_ID` | ID чата для уведомлений о заявках |
| `METRIKA_TOKEN` | OAuth-токен Яндекс.Метрики |
| `METRIKA_COUNTER_ID` | ID счётчика Метрики |
| `GOAL_BOT_STARTED` | ID цели «Бот запущен» |
| `GOAL_LEAD_RECEIVED` | ID цели «Заявка получена» |
| `VIDEO_KEY_GOAL` | file_id/URL видео «Ключевая цель» |
| `VIDEO_ACCESS_INSTRUCTION` | file_id/URL видео «Инструкция по доступу» |
| `VIDEO_WHY_PAID` | file_id/URL видео «Почему аудит платный» |
| `VIDEO_PRICE_REMINDER` | file_id/URL видео к напоминанию о цене |

## Добавление медиа

Видео можно прикреплять двумя способами:

1. **По URL** — прямая ссылка на видеофайл (mp4):
   ```
   VIDEO_KEY_GOAL=https://example.com/video.mp4
   ```

2. **По file_id** — отправьте видео боту, получите file_id из API:
   ```
   VIDEO_KEY_GOAL=BAACAgIAAxkBAAI...
   ```

Если переменная пуста — видео не отправляется, показывается только текст.

## Деплой на VDS

```bash
# На сервере
cd /home/direct/Auditbot
uv sync --locked
```

Для стабильной работы 24/7 запускайте через systemd (аналогично Qualbot).

Unit-файл уже лежит в репозитории: `auditbot.service`.

Для справки, его содержимое:

```ini
[Unit]
Description=Auditbot Telegram Bot Service
After=network.target

[Service]
Type=simple
User=direct
WorkingDirectory=/home/direct/Auditbot
ExecStart=/home/direct/.local/bin/uv run bot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp ./auditbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable auditbot.service
sudo systemctl start auditbot.service

# Логи
sudo journalctl -u auditbot.service -f
```
