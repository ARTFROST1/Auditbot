# Auditbot

Telegram-бот воронки для привлечения клиентов на платный аудит Яндекс.Директа.

## Архитектура

```
Auditbot/
├── bot.py           # Точка входа, FSM-хендлеры, таймауты
├── config.py        # Переменные окружения из .env
├── logger.py        # Логирование (консоль + файл)
├── messages.py      # Тексты сообщений, inline-клавиатуры, callback-константы
├── metrika.py       # Сервис оффлайн-конверсий Яндекс.Метрики
├── bot_schema.md    # Схема логики бота (wireframes)
├── pyproject.toml   # Зависимости (UV)
├── .env.example     # Шаблон переменных окружения
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

Для запуска через systemd создайте сервис `/etc/systemd/system/auditbot.service`:

```ini
[Unit]
Description=Auditbot Telegram Bot
After=network.target

[Service]
Type=simple
User=direct
WorkingDirectory=/home/direct/Auditbot
ExecStart=/home/direct/.local/bin/uv run bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable auditbot
sudo systemctl start auditbot
sudo journalctl -u auditbot -f
```
