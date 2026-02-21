"""Сервис отправки оффлайн-конверсий в Яндекс.Метрику."""

import csv
import io
import time

import httpx

import config
from logger import logger


class MetrikaService:
    """Загрузка оффлайн-конверсий через Management API Яндекс.Метрики.

    Используется для фиксации двух ключевых событий воронки:
    1. Бот запущен (GOAL_BOT_STARTED)
    2. Заявка получена (GOAL_LEAD_RECEIVED)

    Если пользователь пришёл по deep-link с ClientId
    (например /start cid_1234567890), используется этот ClientId.
    Иначе используется Telegram user_id как fallback-идентификатор.
    """

    BASE_URL = "https://api-metrika.yandex.net/management/v1"

    @classmethod
    async def send_conversion(
        cls,
        client_id: str | None,
        goal_id: str,
        tg_user_id: int,
    ) -> bool:
        """Отправляет одну оффлайн-конверсию в Метрику.

        Args:
            client_id: ClientId из Метрики (из deep-link). Может быть None.
            goal_id: ID цели в Метрике.
            tg_user_id: Telegram user ID (используется как fallback).

        Returns:
            True если конверсия успешно отправлена, иначе False.
        """
        if not all([config.METRIKA_TOKEN, config.METRIKA_COUNTER_ID, goal_id]):
            logger.debug(
                "Метрика не настроена (токен/счётчик/цель) — "
                "конверсия не отправлена"
            )
            return False

        cid = client_id or str(tg_user_id)
        timestamp = str(int(time.time()))

        # Формируем CSV
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["ClientId", "Target", "DateTime"])
        writer.writerow([cid, goal_id, timestamp])
        csv_content = buf.getvalue()

        try:
            headers = {"Authorization": f"OAuth {config.METRIKA_TOKEN}"}
            files = {"file": ("conversion.csv", csv_content)}
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(
                    f"{cls.BASE_URL}/counter/{config.METRIKA_COUNTER_ID}"
                    "/offline_conversions/upload",
                    headers=headers,
                    files=files,
                )
            if res.status_code == 200:
                logger.info(
                    f"✅ Конверсия отправлена: goal={goal_id}, cid={cid}"
                )
                return True
            else:
                logger.error(
                    f"❌ Ошибка Метрики: {res.status_code} — {res.text}"
                )
                return False
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке конверсии: {e}")
            return False
