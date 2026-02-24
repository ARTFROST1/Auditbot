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

# ── Яндекс.Метрика ───────────────────────────────────────
METRIKA_TOKEN: str = os.getenv("METRIKA_TOKEN", "")
METRIKA_COUNTER_ID: str = os.getenv("METRIKA_COUNTER_ID", "")
GOAL_BOT_STARTED: str = os.getenv("GOAL_BOT_STARTED", "")     # ID цели «Бот запущен»
GOAL_LEAD_RECEIVED: str = os.getenv("GOAL_LEAD_RECEIVED", "")  # ID цели «Заявка получена»

# ── Таймауты (секунды) ───────────────────────────────────
GREETING_DELAY: int = int(os.getenv("GREETING_DELAY", "5"))
GOAL_REMINDER_TIMEOUT: int = int(os.getenv("GOAL_REMINDER_TIMEOUT", "300"))        # 10 мин
ACCESS_REMINDER_TIMEOUT: int = int(os.getenv("ACCESS_REMINDER_TIMEOUT", "300"))    # 10 мин
PRICE_REMINDER_TIMEOUT: int = int(os.getenv("PRICE_REMINDER_TIMEOUT", "300"))    # 24 ч
FINAL_REMINDER_TIMEOUT: int = int(os.getenv("FINAL_REMINDER_TIMEOUT", "300"))    # 24 ч

# ── Медиа (file_id / URL видео — заполнить позже) ────────
VIDEO_KEY_GOAL: str = os.getenv("VIDEO_KEY_GOAL", "")              # «Что такое ключевая цель»
VIDEO_ACCESS_INSTRUCTION: str = os.getenv("VIDEO_ACCESS_INSTRUCTION", "")  # Инструкция по доступу
VIDEO_WHY_PAID: str = os.getenv("VIDEO_WHY_PAID", "")              # «Почему аудит платный»
VIDEO_PRICE_REMINDER: str = os.getenv("VIDEO_PRICE_REMINDER", "")  # Видео к напоминанию о цене

# ── Ссылки ────────────────────────────────────────────────
TG_CHANNEL_LINK: str = os.getenv("TG_CHANNEL_LINK", "https://t.me/kirill_i_ta")
TG_CHANNEL_HANDLE: str = os.getenv("TG_CHANNEL_HANDLE", "@kirill_i_ta")
CONTACT_PHONE: str = os.getenv("CONTACT_PHONE", "+7-918-422-23-57")
CONTACT_TG: str = os.getenv("CONTACT_TG", "@sargos")
