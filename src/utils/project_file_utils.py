"""
Утилиты для работы с файлами проектов GeoOffice.
Содержит статические методы для обнаружения, анализа и управления файлами проектов.
"""
import json
import os
import traceback
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List

from src.utils.logger_config import get_logger, log_exception
from src import PROJECT_FILE_NAME

logger = get_logger("utils.project_files")


class ProjectFileUtils:
    """
    Утилиты для работы с файлами проектов GeoOffice (.geo_office_project).
    Предоставляет статические методы для обнаружения, анализа и управления файлами проектов.
    """

    @staticmethod
    @log_exception
    def read_project_file(file_path: str | Path) -> str | None:
        """
        Читает файл проекта.
        :param file_path: Путь к файлу
        :return: Содержимое файла или None при ошибке
        """
        try:
            with file_path.open("r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {file_path}: {e}")
            return None

    @staticmethod
    @log_exception
    def is_uid(uid: str) -> bool:
        """
        Проверяет, является ли строка валидным UUID.

        Метод проверяет, соответствует ли переданная строка формату UUID версии 4.
        UUID должен быть в формате с фигурными скобками, например: {12345678-1234-5678-1234-567812345678}

        :param uid: Строка для проверки на соответствие формату UUID
        :return: True, если строка является валидным UUID, иначе False
        """
        if uid == "":
            return False
        try:
            uuid.UUID("{" + f"{uid}" + "}")
            return True
        except ValueError:
            logger.info(f"Некорректный формат UID: {uid}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при проверке UID {uid}: {str(e)}")
            return False

    @staticmethod
    @log_exception
    def set_uid(file_path: str | Path) -> str | None:
        """
        Добавляет UUID в указанный файл.
        :param file_path: Путь к файлу, в который необходимо добавить UUID
        :return: Строка UUID или None при ошибке
        """
        # Создаем новый UID и записываем в файл
        logger.debug(f"Добавление UID в файл `{file_path}`")
        uid = str(uuid.uuid4())
        try:
            with Path(file_path).open("w", encoding="utf-8") as f:
                f.write(uid)
            logger.debug(f"Записан новый UID `{uid}` в файл проекта: `{file_path}`")
            return uid
        except Exception:
            logger.error(f"Ошибка при записи UID в файл {file_path}: {traceback.format_exc()}")
            return None
