"""Конфигурация Auditbot — все настройки из .env.

Важно: загружаем `.env` детерминированно (рядом с этим файлом)
и с `override=True`, чтобы переменные из окружения не "перебивали"
актуальные значения из проекта.
"""

import os

from dotenv import load_dotenv

_dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=_dotenv_path, override=True)

# ── Telegram ──────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID: str = os.getenv("ADMIN_CHAT_ID", "")  # ID чата для уведомлений о лидах
ADMIN_USER_ID: str = os.getenv("ADMIN_USER_ID", "")  # ID админа (личка) для debug-команд/ответов

# ── Яндекс.Метрика ───────────────────────────────────────
METRIKA_TOKEN: str = os.getenv("METRIKA_TOKEN", "")
METRIKA_COUNTER_ID: str = os.getenv("METRIKA_COUNTER_ID", "")
GOAL_BOT_STARTED: str = os.getenv("GOAL_BOT_STARTED", "")     # ID цели «Бот запущен» (/start)
GOAL_STEP1: str = os.getenv("GOAL_STEP1", "")                  # ID цели «Вопрос 1 показан»
GOAL_STEP2: str = os.getenv("GOAL_STEP2", "")                  # ID цели «Вопрос 2 показан»
GOAL_NOT_ENOUGH: str = os.getenv("GOAL_NOT_ENOUGH", "")        # ID цели «Отказ — мало данных»
GOAL_STEP3: str = os.getenv("GOAL_STEP3", "")                  # ID цели «Ключевая цель показана»
GOAL_NO_TARGET: str = os.getenv("GOAL_NO_TARGET", "")          # ID цели «Напоминание о цели (10 мин)»
GOAL_ACCESS: str = os.getenv("GOAL_ACCESS", "")                # ID цели «Запрос доступа показан»
GOAL_NO_ACCESS: str = os.getenv("GOAL_NO_ACCESS", "")          # ID цели «Напоминание о доступе (10 мин)»
GOAL_PRICE: str = os.getenv("GOAL_PRICE", "")                  # ID цели «Стоимость показана»
GOAL_SUB: str = os.getenv("GOAL_SUB", "")                      # ID цели «Скидка применена (подписка на канал)»
GOAL_ANOTHER_BILL: str = os.getenv("GOAL_ANOTHER_BILL", "")    # ID цели «Другой способ оплаты»
GOAL_HIGH_PRICE: str = os.getenv("GOAL_HIGH_PRICE", "")        # ID цели «Напоминание о цене (24ч)»
GOAL_NO_REACTION: str = os.getenv("GOAL_NO_REACTION", "")      # ID цели «Финальное напоминание»
GOAL_ORDER_WITH_PHONE: str = os.getenv("GOAL_ORDER_WITH_PHONE", "")          # ID цели «Заявка с телефоном (без оплаты)»
GOAL_ORDER_NO_PHONE: str = os.getenv("GOAL_ORDER_NO_PHONE", "")              # ID цели «Заявка без телефона (без оплаты)»
GOAL_ORDER_PRICE_WITH_PHONE: str = os.getenv("GOAL_ORDER_PRICE_WITH_PHONE", "")  # ID цели «Готов оплатить + телефон»
GOAL_ORDER_PRICE_NO_PHONE: str = os.getenv("GOAL_ORDER_PRICE_NO_PHONE", "")      # ID цели «Готов оплатить без телефона»

# ── Таймауты (секунды) ───────────────────────────────────
GREETING_DELAY: int = int(os.getenv("GREETING_DELAY", "5"))
GOAL_REMINDER_TIMEOUT: int = int(os.getenv("GOAL_REMINDER_TIMEOUT", "600"))        # 10 мин
ACCESS_REMINDER_TIMEOUT: int = int(os.getenv("ACCESS_REMINDER_TIMEOUT", "600"))    # 10 мин
PRICE_REMINDER_TIMEOUT: int = int(os.getenv("PRICE_REMINDER_TIMEOUT", "86400"))    # 24 ч
FINAL_REMINDER_TIMEOUT: int = int(os.getenv("FINAL_REMINDER_TIMEOUT", "86400"))    # 24 ч

# ── Медиа (file_id / URL видео — заполнить позже) ────────
# По умолчанию переменные VIDEO_* отправляются как обычное видео (send_video).
# Если нужно отправить «кружок» (video_note) — используйте префикс:
#   VIDEO_GREETING=note:<file_id>
#   VIDEO_GREETING=video_note:<file_id>
VIDEO_GREETING: str = os.getenv("VIDEO_GREETING", "")              # Видео 1 — «Кто я, есть ли цель у аккаунта» — приветствие
VIDEO_KEY_GOAL: str = os.getenv("VIDEO_KEY_GOAL", "")              # Видео 2 — «Три уровня аудита» — ключевая цель
VIDEO_ACCESS_INSTRUCTION: str = os.getenv("VIDEO_ACCESS_INSTRUCTION", "")  # Видео 3 — «Ваши данные — только ваши» — запрос доступа
VIDEO_GOAL_REMINDER: str = os.getenv("VIDEO_GOAL_REMINDER", "")    # Видео 4 — «Аудит — идеи, не критика» — напоминание о цели
VIDEO_ABOUT_ME: str = os.getenv("VIDEO_ABOUT_ME", "")              # Видео 5 — «О себе / экспертиза» — отказ и напоминание о доступе
VIDEO_WHY_PAID: str = os.getenv("VIDEO_WHY_PAID", "")              # Видео 6 — «Почему аудит платный» — стоимость
VIDEO_PRICE_REMINDER: str = os.getenv("VIDEO_PRICE_REMINDER", "")  # Видео 7 — «Лотерейный билет» — напоминание о цене

# ── Ссылки ────────────────────────────────────────────────
TG_CHANNEL_LINK: str = os.getenv("TG_CHANNEL_LINK", "https://t.me/kirill_i_ta")
TG_CHANNEL_HANDLE: str = os.getenv("TG_CHANNEL_HANDLE", "@kirill_i_ta")
CONTACT_PHONE: str = os.getenv("CONTACT_PHONE", "+7-918-422-23-57")
CONTACT_TG: str = os.getenv("CONTACT_TG", "@sargos")
