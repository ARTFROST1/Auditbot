"""Настройка логирования для Auditbot."""

import logging
import os

logger = logging.getLogger("auditbot")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

# Консольный вывод
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Файловый лог
log_path = os.path.join(os.path.dirname(__file__), "logs.log")
file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
