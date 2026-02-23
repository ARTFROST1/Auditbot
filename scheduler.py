"""Персистентный планировщик напоминаний для Auditbot.

ЗАЧЕМ:
    asyncio.Task живут только в памяти процесса. При любом перезапуске
    сервиса (systemd Restart=always) все незавершённые таймеры теряются, и
    24-часовые напоминания никогда не достигают пользователя.

КАК РАБОТАЕТ:
    - Каждое запланированное напоминание сохраняется в reminders.json рядом
      с botом (время срабатывания, тип callback, ожидаемое FSM-состояние).
    - При перезапуске бота вызывается restore_on_startup(), которая читает файл,
      восстанавливает FSM-состояния пользователей и пересоздаёт asyncio-задачи
      с оставшимся временем.
    - Когда напоминание срабатывает (или отменяется) — запись удаляется из файла.

ОГРАНИЧЕНИЯ:
    - Если сервер лежит дольше задержки, напоминание отправляется сразу
      после подъёма (с паузой 10 секунд на инициализацию).
    - Один активный напоминатель на пользователя. Если нужен следующий шаг,
      хендлер сам планирует новый через scheduler.schedule().
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Awaitable, Callable

from logger import logger

# ── Пути ──────────────────────────────────────────────────
_REMINDERS_FILE = os.path.join(os.path.dirname(__file__), "reminders.json")

# ── Реестры ───────────────────────────────────────────────
# callback_type -> async def handler(user_id: int) -> None
_handlers: dict[str, Callable[[int], Awaitable[None]]] = {}

# user_id -> asyncio.Task
_tasks: dict[int, asyncio.Task] = {}

# async def restorer(user_id: int, state: str) -> None
_state_restorer: Callable[[int, str], Awaitable[None]] | None = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Публичный API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def set_state_restorer(
    fn: Callable[[int, str], Awaitable[None]],
) -> None:
    """Зарегистрировать callback для восстановления FSM-состояния при рестарте."""
    global _state_restorer
    _state_restorer = fn


def register_handler(
    callback_type: str,
    handler: Callable[[int], Awaitable[None]],
) -> None:
    """Связать строковый тип напоминания с async-обработчиком."""
    _handlers[callback_type] = handler


def schedule(
    user_id: int,
    callback_type: str,
    delay: int,
    expected_state: str = "",
) -> None:
    """Запланировать напоминание.

    Args:
        user_id:        Telegram user ID.
        callback_type:  Ключ зарегистрированного обработчика.
        delay:          Задержка в секундах.
        expected_state: FSM-состояние, которое будет восстановлено при рестарте
                        перед вызовом обработчика (нужно, чтобы хендлер прошёл
                        проверку ``await ctx.get_state() == ...``).
    """
    cancel(user_id)

    fire_at = time.time() + delay
    data = _load()
    data[str(user_id)] = {
        "callback_type": callback_type,
        "fire_at": fire_at,
        "expected_state": expected_state,
    }
    _save(data)

    _create_task(user_id, callback_type, delay)
    logger.debug(
        f"[scheduler] Запланировано '{callback_type}' user={user_id} "
        f"через {delay} сек"
    )


def cancel(user_id: int) -> None:
    """Отменить запланированное напоминание для пользователя (если есть)."""
    task = _tasks.pop(user_id, None)
    if task and not task.done():
        # Никогда не отменяем задачу изнутри самой себя — она завершится сама.
        if task is not asyncio.current_task():
            task.cancel()

    data = _load()
    if str(user_id) in data:
        del data[str(user_id)]
        _save(data)


async def restore_on_startup() -> None:
    """Восстановить незавершённые напоминания после перезапуска бота.

    Должна вызываться один раз в main() после инициализации бота и
    регистрации всех хендлеров.
    """
    data = _load()
    if not data:
        logger.info("[scheduler] Нет сохранённых напоминаний для восстановления")
        return

    now = time.time()
    restored = 0

    for user_id_str, entry in list(data.items()):
        user_id = int(user_id_str)
        callback_type = entry.get("callback_type", "")
        fire_at = float(entry.get("fire_at", 0))
        expected_state = entry.get("expected_state", "")

        if not callback_type:
            continue

        # Восстанавливаем FSM-состояние, чтобы хендлер прошёл state-проверку.
        if expected_state and _state_restorer:
            try:
                await _state_restorer(user_id, expected_state)
                logger.debug(
                    f"[scheduler] FSM user={user_id} восстановлено: {expected_state}"
                )
            except Exception as exc:
                logger.warning(
                    f"[scheduler] Не удалось восстановить FSM user={user_id}: {exc}"
                )

        # Оставшееся время. Минимум 10 сек — чтобы бот успел полностью запуститься
        # перед тем, как начнут стрелять отложенные сообщения.
        remaining = max(10.0, fire_at - now)
        logger.info(
            f"[scheduler] Восстановлено: '{callback_type}' user={user_id} "
            f"через {remaining:.0f} сек "
            f"({'просрочено' if fire_at < now else 'в срок'})"
        )
        _create_task(user_id, callback_type, remaining)
        restored += 1

    logger.info(f"[scheduler] Итого восстановлено напоминаний: {restored}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Внутренние утилиты
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load() -> dict:
    if not os.path.exists(_REMINDERS_FILE):
        return {}
    try:
        with open(_REMINDERS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning(f"[scheduler] reminders.json не читается: {exc}")
        return {}


def _save(data: dict) -> None:
    try:
        with open(_REMINDERS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning(f"[scheduler] reminders.json не записывается: {exc}")


def _create_task(user_id: int, callback_type: str, delay: float) -> None:
    """Создать asyncio-задачу для напоминания."""

    async def _run() -> None:
        try:
            await asyncio.sleep(max(0.0, delay))
            handler = _handlers.get(callback_type)
            if handler is None:
                logger.error(
                    f"[scheduler] Обработчик не найден: '{callback_type}'"
                )
                return
            await handler(user_id)
        except asyncio.CancelledError:
            # Штатная отмена — молча выходим.
            pass
        except Exception as exc:
            logger.error(
                f"[scheduler] Ошибка в '{callback_type}' user={user_id}: {exc}"
            )
        finally:
            # Удаляем из словаря только если мы всё ещё текущая задача.
            # Если внутри хендлера был вызван scheduler.schedule(), то
            # _tasks[user_id] уже указывает на НОВУЮ задачу — не трогаем её.
            if _tasks.get(user_id) is asyncio.current_task():
                _tasks.pop(user_id, None)

            # Удаляем из файла только если там ещё наш тип callback.
            # Если schedule() заменил запись на новый тип — не трогаем.
            try:
                data = _load()
                entry = data.get(str(user_id), {})
                if entry.get("callback_type") == callback_type:
                    del data[str(user_id)]
                    _save(data)
            except Exception as exc:
                logger.warning(f"[scheduler] Ошибка cleanup reminders.json: {exc}")

    task = asyncio.create_task(_run())
    _tasks[user_id] = task
