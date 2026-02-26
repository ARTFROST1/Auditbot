"""Auditbot — Telegram-бот воронки для привлечения на платный аудит Директа.

Полная логика FSM-воронки с таймаутами, inline-кнопками,
отправкой оффлайн-конверсий в Яндекс.Метрику
и уведомлениями администратору.
"""

import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.filters import BaseFilter, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

import config
import scheduler
from logger import logger
from messages import (
    CB_ACCESS_REM_WRITE,
    CB_ACCESS_REM_YES,
    CB_ACCESS_YES,
    CB_GOAL_AUDIT,
    CB_INDIVIDUAL_WRITE,
    CB_PRICE_NO,
    CB_PRICE_REM_PAY,
    CB_PRICE_REM_WRITE,
    CB_PRICE_YES,
    CB_Q1_NO,
    CB_Q1_YES,
    CB_Q2_100K_NO,
    CB_Q2_100K_YES,
    CB_Q2_50K_NO,
    CB_Q2_50K_YES,
    CB_REJECT_APPLY,
    KB_ACCESS_REMINDER,
    KB_ACCESS_REQUEST,
    KB_GOAL_REMINDER,
    KB_INDIVIDUAL,
    KB_PHONE_REMOVE,
    KB_PHONE_REQUEST,
    KB_PRICE,
    KB_PRICE_REMINDER,
    KB_QUESTION_1,
    KB_QUESTION_2_100K,
    KB_QUESTION_2_50K,
    KB_REJECT,
    MSG_ACCESS_REMINDER,
    MSG_ACCESS_REQUEST,
    MSG_FINAL_REMINDER,
    MSG_GOAL_REMINDER,
    MSG_GREETING,
    MSG_INDIVIDUAL,
    MSG_KEY_GOAL,
    MSG_LEAD_REQUISITES,
    MSG_LEAD_SHORT,
    MSG_PHONE_REQUEST,
    MSG_PRICE,
    MSG_PRICE_REMINDER,
    MSG_QUESTION_1,
    MSG_QUESTION_2_100K,
    MSG_QUESTION_2_50K,
    MSG_REJECT,
    admin_notification,
    kb_channel_link,
)
from metrika import MetrikaService

# ── Инициализация ─────────────────────────────────────────
# Bot и Dispatcher создаются в main(), чтобы не падать при импорте
# без валидного токена (например, при тестах или проверке синтаксиса)
bot: Bot = None  # type: ignore[assignment]
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()


# ── FSM-состояния воронки ─────────────────────────────────
class Funnel(StatesGroup):
    """Машина состояний воронки аудита."""

    greeting = State()          # Приветствие показано, ждём 5 сек
    question_1 = State()        # Вопрос 1 показан
    question_2_50k = State()    # Вопрос 2 (бюджет > 50k)
    question_2_100k = State()   # Вопрос 2 (бюджет > 100k)
    reject = State()            # Отказ — мало данных
    key_goal = State()          # Ждём текст про ключевую цель
    goal_reminder = State()     # Напоминание — не ответил про цель
    access_request = State()    # Запрос доступа
    access_reminder = State()   # Напоминание — не дал доступ
    price = State()             # Стоимость показана
    price_reminder = State()    # Напоминание — стоимость
    individual = State()        # Индивидуальный формат
    phone_request = State()     # Запрос номера телефона перед финализацией
    finished = State()          # Воронка завершена


# ── Вспомогательные функции FSM ──────────────────────────
_bot_id: int | None = None


async def _get_bot_id() -> int:
    """Получить и закешировать ID бота."""
    global _bot_id
    if _bot_id is None:
        me = await bot.get_me()
        _bot_id = me.id
    return _bot_id


async def _get_state_ctx(user_id: int) -> FSMContext:
    """Создать FSMContext для пользователя вне хендлера."""
    bot_id = await _get_bot_id()
    key = StorageKey(bot_id=bot_id, chat_id=user_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


# ── Обработчики напоминаний (регистрируются в main()) ─────
# Каждый handler — это top-level async-функция, принимающая user_id.
# Они передаются в персистентный scheduler, который сохраняет их
# в reminders.json и восстанавливает после перезапуска бота.

async def _hdl_goal_reminder(user_id: int) -> None:
    """Напоминание: не ответил о ключевой цели (10 мин → шаг goal_reminder)."""
    ctx = await _get_state_ctx(user_id)
    if await ctx.get_state() == Funnel.key_goal.state:
        await _send_step(
            user_id, MSG_GOAL_REMINDER, keyboard=KB_GOAL_REMINDER,
            video=config.VIDEO_GOAL_REMINDER,
        )
        await ctx.set_state(Funnel.goal_reminder)
        scheduler.schedule(
            user_id, "goal_final", config.FINAL_REMINDER_TIMEOUT,
            expected_state=Funnel.goal_reminder.state,
        )


async def _hdl_goal_final(user_id: int) -> None:
    """Финал: не нажал кнопку 24ч после напоминания о цели."""
    ctx = await _get_state_ctx(user_id)
    if await ctx.get_state() == Funnel.goal_reminder.state:
        await _send_step(user_id, MSG_FINAL_REMINDER)
        await ctx.set_state(Funnel.finished)


async def _hdl_access_reminder(user_id: int) -> None:
    """Напоминание: не выдал доступ (10 мин → шаг access_reminder)."""
    ctx = await _get_state_ctx(user_id)
    if await ctx.get_state() == Funnel.access_request.state:
        await _send_step(
            user_id, MSG_ACCESS_REMINDER, keyboard=KB_ACCESS_REMINDER,
            video=config.VIDEO_ABOUT_ME,
        )
        await ctx.set_state(Funnel.access_reminder)
        scheduler.schedule(
            user_id, "access_final", config.FINAL_REMINDER_TIMEOUT,
            expected_state=Funnel.access_reminder.state,
        )


async def _hdl_access_final(user_id: int) -> None:
    """Финал: не выдал доступ 24ч после напоминания."""
    ctx = await _get_state_ctx(user_id)
    if await ctx.get_state() == Funnel.access_reminder.state:
        await _send_step(user_id, MSG_FINAL_REMINDER)
        await ctx.set_state(Funnel.finished)


async def _hdl_price_reminder(user_id: int) -> None:
    """Напоминание: не ответил на стоимость (24ч → шаг price_reminder)."""
    ctx = await _get_state_ctx(user_id)
    if await ctx.get_state() == Funnel.price.state:
        await _send_step(
            user_id,
            MSG_PRICE_REMINDER,
            keyboard=KB_PRICE_REMINDER,
            video=config.VIDEO_PRICE_REMINDER,
        )
        await ctx.set_state(Funnel.price_reminder)
        scheduler.schedule(
            user_id, "price_final", config.FINAL_REMINDER_TIMEOUT,
            expected_state=Funnel.price_reminder.state,
        )


async def _hdl_price_final(user_id: int) -> None:
    """Финал: не оплатил 24ч после напоминания о цене."""
    ctx = await _get_state_ctx(user_id)
    if await ctx.get_state() == Funnel.price_reminder.state:
        await _send_step(user_id, MSG_FINAL_REMINDER)
        await ctx.set_state(Funnel.finished)


# ── Вспомогательная отправка шага ─────────────────────────
async def _send_step(
    chat_id: int,
    text: str,
    keyboard=None,
    video: str = "",
) -> None:
    """Отправить сообщение воронки, при наличии — с видео перед ним."""
    if video:
        payload = video.strip()
        try:
            # Поддержка кружка (video_note) через префикс в .env:
            #   VIDEO_KEY_GOAL=note:<file_id>
            # По умолчанию (без префикса) отправляем обычное видео.
            if payload.startswith(("note:", "video_note:")):
                file_id = payload.split(":", 1)[1].strip()
                if file_id:
                    await bot.send_video_note(chat_id, file_id)
            else:
                await bot.send_video(chat_id, payload)
        except Exception as e:
            logger.warning(f"Не удалось отправить видео/кружок: {e}")
    await bot.send_message(
        chat_id, text, parse_mode="HTML", reply_markup=keyboard,
    )


async def _remove_buttons(callback: CallbackQuery) -> None:
    """Убрать inline-кнопки из сообщения после нажатия."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass  # Сообщение уже отредактировано или удалено


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  /start — Запуск воронки
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик /start — начало воронки.

    Deep-link формат для передачи ClientId из Метрики:
        /start cid_1234567890
    """
    user_id = message.from_user.id
    scheduler.cancel(user_id)
    await state.clear()

    # Извлекаем ClientId из deep-link (если есть)
    client_id = None
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("cid_"):
        client_id = args[1][4:]

    await state.update_data(
        client_id=client_id,
        tg_user_id=user_id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or "",
    )

    # Отправляем приветствие (+ видео-визитка, если задано)
    await state.set_state(Funnel.greeting)
    await _send_step(user_id, MSG_GREETING, video=config.VIDEO_GREETING)

    # Метрика: бот запущен
    asyncio.create_task(
        MetrikaService.send_conversion(
            client_id, config.GOAL_BOT_STARTED, user_id,
        )
    )

    # Таймаут 5 сек → автоматически отправляем Вопрос 1.
    # Эту короткую задержку не персистируем — потеря при рестарте некритична.
    # Проверка статуса реализует идемпотентность: если статус уже не greeting — 
    # значит, пользователь уже продвинулся и отправлять вопрос не нужно.
    async def _greeting_delay() -> None:
        await asyncio.sleep(config.GREETING_DELAY)
        ctx = await _get_state_ctx(user_id)
        if await ctx.get_state() == Funnel.greeting.state:
            await _send_step(
                user_id, MSG_QUESTION_1, keyboard=KB_QUESTION_1,
            )
            await ctx.set_state(Funnel.question_1)

    asyncio.create_task(_greeting_delay())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Вопрос 1: Реклама работала последние 3 месяца?
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == CB_Q1_YES)
async def on_q1_yes(callback: CallbackQuery, state: FSMContext):
    scheduler.cancel(callback.from_user.id)
    await callback.answer()
    await _remove_buttons(callback)
    await state.update_data(ad_worked="Да")
    await _send_step(
        callback.from_user.id,
        MSG_QUESTION_2_50K,
        keyboard=KB_QUESTION_2_50K,
    )
    await state.set_state(Funnel.question_2_50k)


@router.callback_query(F.data == CB_Q1_NO)
async def on_q1_no(callback: CallbackQuery, state: FSMContext):
    scheduler.cancel(callback.from_user.id)
    await callback.answer()
    await _remove_buttons(callback)
    await state.update_data(ad_worked="Нет")
    await _send_step(
        callback.from_user.id,
        MSG_QUESTION_2_100K,
        keyboard=KB_QUESTION_2_100K,
    )
    await state.set_state(Funnel.question_2_100k)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Вопрос 2: Бюджет
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _handle_budget_yes(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    """Бюджет достаточный → переход к ключевой цели."""
    user_id = callback.from_user.id
    scheduler.cancel(user_id)
    await callback.answer()
    await _remove_buttons(callback)
    await state.update_data(budget_ok="Да")

    # Отправляем вопрос о ключевой цели (+ видео, если задано)
    await _send_step(
        user_id, MSG_KEY_GOAL, video=config.VIDEO_KEY_GOAL,
    )
    await state.set_state(Funnel.key_goal)

    # Таймер 10 мин → напоминание о цели (персистентный)
    scheduler.schedule(
        user_id, "goal_reminder", config.GOAL_REMINDER_TIMEOUT,
        expected_state=Funnel.key_goal.state,
    )


async def _handle_budget_no(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    """Бюджет недостаточный → отказ."""
    scheduler.cancel(callback.from_user.id)
    await callback.answer()
    await _remove_buttons(callback)
    await state.update_data(budget_ok="Нет")
    await _send_step(
        callback.from_user.id, MSG_REJECT, keyboard=KB_REJECT,
        video=config.VIDEO_ABOUT_ME,
    )
    await state.set_state(Funnel.reject)


@router.callback_query(F.data == CB_Q2_50K_YES)
async def on_q2_50k_yes(callback: CallbackQuery, state: FSMContext):
    await _handle_budget_yes(callback, state)


@router.callback_query(F.data == CB_Q2_50K_NO)
async def on_q2_50k_no(callback: CallbackQuery, state: FSMContext):
    await _handle_budget_no(callback, state)


@router.callback_query(F.data == CB_Q2_100K_YES)
async def on_q2_100k_yes(callback: CallbackQuery, state: FSMContext):
    await _handle_budget_yes(callback, state)


@router.callback_query(F.data == CB_Q2_100K_NO)
async def on_q2_100k_no(callback: CallbackQuery, state: FSMContext):
    await _handle_budget_no(callback, state)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Отказ → Оставить заявку
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == CB_REJECT_APPLY)
async def on_reject_apply(callback: CallbackQuery, state: FSMContext):
    await _send_lead_short(callback, state)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Ключевая цель — текстовый ответ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message(Funnel.key_goal)
async def on_key_goal_text(message: Message, state: FSMContext):
    """Пользователь написал текстом свою ключевую цель."""
    scheduler.cancel(message.from_user.id)
    await state.update_data(key_goal=message.text)
    await _send_access_request(message.from_user.id, state)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Напоминание 1 → Перейти к аудиту
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == CB_GOAL_AUDIT)
async def on_goal_audit(callback: CallbackQuery, state: FSMContext):
    scheduler.cancel(callback.from_user.id)
    await callback.answer()
    await _remove_buttons(callback)
    await state.update_data(key_goal="(не указана — перешёл к аудиту)")
    await _send_access_request(callback.from_user.id, state)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Отправка запроса доступа (хелпер)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_access_request(
    user_id: int, state: FSMContext,
) -> None:
    """Показать сообщение 8 — запрос доступа к Директу и Метрике."""
    await _send_step(
        user_id,
        MSG_ACCESS_REQUEST,
        keyboard=KB_ACCESS_REQUEST,
        video=config.VIDEO_ACCESS_INSTRUCTION,
    )
    await state.set_state(Funnel.access_request)

    # Таймер 10 мин → напоминание о доступе (персистентный)
    scheduler.schedule(
        user_id, "access_reminder", config.ACCESS_REMINDER_TIMEOUT,
        expected_state=Funnel.access_request.state,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Доступ: согласие
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == CB_ACCESS_YES)
async def on_access_yes(callback: CallbackQuery, state: FSMContext):
    scheduler.cancel(callback.from_user.id)
    await callback.answer()
    await _remove_buttons(callback)
    await _send_price(callback.from_user.id, state)


@router.callback_query(F.data == CB_ACCESS_REM_YES)
async def on_access_rem_yes(callback: CallbackQuery, state: FSMContext):
    scheduler.cancel(callback.from_user.id)
    await callback.answer()
    await _remove_buttons(callback)
    await _send_price(callback.from_user.id, state)


@router.callback_query(F.data == CB_ACCESS_REM_WRITE)
async def on_access_rem_write(callback: CallbackQuery, state: FSMContext):
    await _send_lead_short(callback, state)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Отправка стоимости (хелпер)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_price(user_id: int, state: FSMContext) -> None:
    """Показать сообщение 10 — стоимость аудита."""
    await _send_step(
        user_id,
        MSG_PRICE,
        keyboard=KB_PRICE,
        video=config.VIDEO_WHY_PAID,
    )
    await state.set_state(Funnel.price)

    # Таймер 24ч → напоминание о цене (персистентный)
    scheduler.schedule(
        user_id, "price_reminder", config.PRICE_REMINDER_TIMEOUT,
        expected_state=Funnel.price.state,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Цена: ответы
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == CB_PRICE_YES)
async def on_price_yes(callback: CallbackQuery, state: FSMContext):
    await _send_lead_requisites(callback, state)


@router.callback_query(F.data == CB_PRICE_NO)
async def on_price_no(callback: CallbackQuery, state: FSMContext):
    scheduler.cancel(callback.from_user.id)
    await callback.answer()
    await _remove_buttons(callback)
    await _send_step(
        callback.from_user.id, MSG_INDIVIDUAL, keyboard=KB_INDIVIDUAL,
    )
    await state.set_state(Funnel.individual)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Напоминание о цене: кнопки
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == CB_PRICE_REM_PAY)
async def on_price_rem_pay(callback: CallbackQuery, state: FSMContext):
    await _send_lead_requisites(callback, state)


@router.callback_query(F.data == CB_PRICE_REM_WRITE)
async def on_price_rem_write(callback: CallbackQuery, state: FSMContext):
    await _send_lead_short(callback, state)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Индивидуальный формат: напишите мне
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == CB_INDIVIDUAL_WRITE)
async def on_individual_write(callback: CallbackQuery, state: FSMContext):
    await _send_lead_short(callback, state)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Финальные шаги — заявка получена
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_lead_short(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    """Сообщение 13 — Заявка принята (короткая)."""
    user_id = callback.from_user.id
    scheduler.cancel(user_id)
    await callback.answer()
    await _remove_buttons(callback)
    await _request_phone(user_id, state, lead_type="short")


async def _send_lead_requisites(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    """Сообщение 14 — Заявка принята (с реквизитами)."""
    user_id = callback.from_user.id
    scheduler.cancel(user_id)
    await callback.answer()
    await _remove_buttons(callback)
    await _request_phone(user_id, state, lead_type="requisites")


async def _request_phone(
    user_id: int, state: FSMContext, lead_type: str,
) -> None:
    """Показать запрос номера телефона перед отправкой заявки."""
    await state.update_data(pending_lead_type=lead_type)
    await bot.send_message(
        user_id, MSG_PHONE_REQUEST, parse_mode="HTML",
        reply_markup=KB_PHONE_REQUEST,
    )
    await state.set_state(Funnel.phone_request)


async def _finalize_lead(user_id: int, state: FSMContext) -> None:
    """Отправить финальное сообщение, конверсию в Метрику и уведомашь админа."""
    data = await state.get_data()
    lead_type_key = data.get("pending_lead_type", "short")

    if lead_type_key == "requisites":
        msg = MSG_LEAD_REQUISITES
        lead_type_label = "Готов оплатить"
    else:
        msg = MSG_LEAD_SHORT
        lead_type_label = "Запрос связи"

    # Убираем reply-клавиатуру и отправляем подтверждение
    await bot.send_message(
        user_id, msg, parse_mode="HTML", reply_markup=KB_PHONE_REMOVE,
    )
    await state.set_state(Funnel.finished)

    # Метрика: заявка получена
    asyncio.create_task(
        MetrikaService.send_conversion(
            data.get("client_id"),
            config.GOAL_LEAD_RECEIVED,
            user_id,
        )
    )

    # Уведомление админу
    await _notify_admin(data, lead_type=lead_type_label)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Запрос номера телефона: обработка ответа
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message(Funnel.phone_request, F.contact)
async def on_phone_contact(message: Message, state: FSMContext):
    """Пользователь поделился номером через кнопку."""
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await _finalize_lead(message.from_user.id, state)


@router.message(Funnel.phone_request)
async def on_phone_skip(message: Message, state: FSMContext):
    """Пользователь пропустил шаг с номером."""
    await state.update_data(phone="")
    await _finalize_lead(message.from_user.id, state)


async def _notify_admin(data: dict, *, lead_type: str) -> None:
    """Отправить уведомление о новой заявке в чат администратора."""
    if not config.ADMIN_CHAT_ID:
        logger.debug("ADMIN_CHAT_ID не задан — уведомление не отправлено")
        return
    text = admin_notification(
        username=data.get("username", ""),
        full_name=data.get("full_name", ""),
        tg_user_id=data.get("tg_user_id", ""),
        ad_worked=data.get("ad_worked", "—"),
        budget_ok=data.get("budget_ok", "—"),
        key_goal=data.get("key_goal", "—"),
        phone=data.get("phone", ""),
        lead_type=lead_type,
    )
    try:
        await bot.send_message(
            config.ADMIN_CHAT_ID, text, parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить админа: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Admin debug: получить file_id медиа
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class _IsAdminChat(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        # Поддерживаем 2 сценария:
        # 1) ADMIN_CHAT_ID: чат/группа для уведомлений (chat.id)
        # 2) ADMIN_USER_ID: ваш личный user id для debug (from_user.id)
        admin_chat_ok = False
        if config.ADMIN_CHAT_ID:
            try:
                admin_chat_id = int(str(config.ADMIN_CHAT_ID).strip())
                admin_chat_ok = message.chat.id == admin_chat_id
            except ValueError:
                admin_chat_ok = False

        admin_user_ok = False
        if config.ADMIN_USER_ID and message.from_user is not None:
            try:
                admin_user_id = int(str(config.ADMIN_USER_ID).strip())
                admin_user_ok = message.from_user.id == admin_user_id
            except ValueError:
                admin_user_ok = False

        return admin_chat_ok or admin_user_ok


@router.message(_IsAdminChat(), F.video)
async def admin_get_video_file_id(message: Message) -> None:
    file_id = message.video.file_id
    unique_id = message.video.file_unique_id
    await message.answer(
        "file_id (video):\n"
        f"{file_id}\n\n"
        "Можно вставить в .env так:\n"
        f"VIDEO_KEY_GOAL={file_id}\n\n"
        f"file_unique_id: {unique_id}",
    )


@router.message(_IsAdminChat(), F.video_note)
async def admin_get_video_note_file_id(message: Message) -> None:
    file_id = message.video_note.file_id
    unique_id = message.video_note.file_unique_id
    await message.answer(
        "file_id (video_note / кружок):\n"
        f"{file_id}\n\n"
        "Можно вставить в .env так:\n"
        f"VIDEO_KEY_GOAL=note:{file_id}\n\n"
        f"file_unique_id: {unique_id}",
    )


@router.message(_IsAdminChat(), F.document)
async def admin_get_document_file_id(message: Message) -> None:
    # Если видео отправили «как файл», Telegram отдаёт его как document.
    doc = message.document
    mime = (doc.mime_type or "").lower()
    if not mime.startswith("video/"):
        return
    await message.answer(
        "file_id (document video):\n"
        f"{doc.file_id}\n\n"
        "Можно вставить в .env так:\n"
        f"VIDEO_KEY_GOAL={doc.file_id}\n\n"
        f"mime_type: {doc.mime_type}",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Фолбэк: текст в неожиданном состоянии
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message()
async def fallback_message(message: Message, state: FSMContext):
    """Ответ на неожиданные сообщения пользователя."""
    current = await state.get_state()
    if current is None or current == Funnel.finished.state:
        # Пользователь закончил воронку или ещё не начал
        await message.answer(
            "👋 Нажмите <b>/start</b>, чтобы начать!",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "☝️ Пожалуйста, воспользуйтесь кнопками выше.",
            parse_mode="HTML",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Точка входа
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def main():
    """Инициализация и запуск polling."""
    global bot
    if not config.BOT_TOKEN or "..." in config.BOT_TOKEN:
        logger.error(
            "BOT_TOKEN не задан или выглядит как шаблон. "
            "Проверьте файл .env (переменная BOT_TOKEN) и вставьте токен "
            "из @BotFather."
        )
        return
    bot = Bot(token=config.BOT_TOKEN)
    dp.include_router(router)
    logger.info("🚀 Auditbot запущен")
    try:
        # Быстрая проверка токена, чтобы падать с понятной ошибкой
        await bot.get_me()
    except TelegramUnauthorizedError:
        logger.error(
            "Telegram отклонил токен (Unauthorized). "
            "Проверьте BOT_TOKEN в .env: токен должен быть актуальным и "
            "точно скопированным из @BotFather."
        )
        return

    # ── Персистентный планировщик ─────────────────────────
    # Регистрируем обработчики напоминаний (имя → функция).
    scheduler.register_handler("goal_reminder", _hdl_goal_reminder)
    scheduler.register_handler("goal_final", _hdl_goal_final)
    scheduler.register_handler("access_reminder", _hdl_access_reminder)
    scheduler.register_handler("access_final", _hdl_access_final)
    scheduler.register_handler("price_reminder", _hdl_price_reminder)
    scheduler.register_handler("price_final", _hdl_price_final)

    # Callback для восстановления FSM-состояния после рестарта.
    async def _restore_fsm_state(user_id: int, state: str) -> None:
        ctx = await _get_state_ctx(user_id)
        await ctx.set_state(state)

    scheduler.set_state_restorer(_restore_fsm_state)

    # Восстанавливаем отложенные напоминания из reminders.json.
    await scheduler.restore_on_startup()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
