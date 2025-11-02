import os
import json
import re
import subprocess
import platform
from typing import Dict, Any, Optional
from pathlib import Path
from src.utils.logger_config import get_logger, log_exception

logger = get_logger("utils.files")


class FileUtils:
    """
    Утилиты для работы с файлами: сохранение, загрузка, проверка, создание директорий и получение информации о файлах.
    """
    
    @staticmethod
    @log_exception
    def save_json(data: Dict[str, Any], filename: str | Path) -> bool:
        """
        Сохраняет данные в JSON-файл.
        :param data: Словарь с данными
        :param filename: Имя файла для сохранения
        :return: True, если успешно, иначе False
        """
        logger.debug(f"Сохранение JSON файла: {filename}")
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON файл сохранен: {filename}")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения файла {filename}: {str(e)}")
            return False
    
    @staticmethod
    @log_exception
    def load_json(filename: str | Path) -> Optional[Dict[str, Any]]:
        """
        Загружает данные из JSON-файла.
        :param filename: Имя файла для загрузки
        :return: Словарь с данными или None, если ошибка
        """
        """Загрузка данных из JSON файла"""
        logger.debug(f"Загрузка JSON файла: {filename}")
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"JSON файл загружен: {filename}")
                    return data
            else:
                logger.warning(f"Файл не найден: {filename}")
                return None
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON файла {filename}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Ошибка загрузки файла {filename}: {str(e)}")
            return None

    @staticmethod
    @log_exception
    def manage_file_attributes(file_path: str|Path, action: str = "show") -> Dict[str, Any]:
        """
        Управление атрибутами файла в Windows.
        :param file_path: Путь к файлу
        :type file_path: str | Path
        :param action: Действие ("show", "hide", "protect", "unprotect")
        :type action: str
        :return: Словарь с результатом
        :rtype: Dict[str, Any]
        """
        path = Path(file_path)
        result = {
            'file_path': str(path),
            'exists': path.exists(),
            'action': action,
            'success': False,
            'attributes_before': None,
            'attributes_after': None,
            'error': None
        }

        if not path.exists():
            result['error'] = "Файл не существует"
            return result

        try:
            # Получаем атрибуты до изменения
            attrib_result = subprocess.run(['attrib', str(path)],
                                           capture_output=True, text=True, check=True)
            result['attributes_before'] = attrib_result.stdout.strip()

            # Выполняем действие
            if action == "show":
                # Сделать видимым (снять скрытый и системный)
                subprocess.run(['attrib', '-h', '-s', str(path)], check=True)
                result['message'] = "Файл сделан видимым"

            elif action == "hide":
                # Сделать скрытым
                subprocess.run(['attrib', '+h', str(path)], check=True)
                result['message'] = "Файл скрыт"

            elif action == "protect":
                # Защитить (скрытый + системный)
                subprocess.run(['attrib', '+h', '+s', str(path)], check=True)
                result['message'] = "Файл защищен"

            elif action == "unprotect":
                # Снять защиту
                subprocess.run(['attrib', '-h', '-s', '-r', str(path)], check=True)
                result['message'] = "Защита снята"

            # Получаем атрибуты после изменения
            attrib_result = subprocess.run(['attrib', str(path)],
                                           capture_output=True, text=True, check=True)
            result['attributes_after'] = attrib_result.stdout.strip()
            result['success'] = True

        except subprocess.CalledProcessError as e:
            result['error'] = f"Ошибка выполнения команды: {e}"
        except Exception as e:
            result['error'] = f"Неожиданная ошибка: {e}"

        return result

    @staticmethod
    @log_exception
    def get_relative_path(path: str | Path, subpath: str | Path) -> str | None:
        """
        Вычисляет относительный путь.
        :param path: Родительский путь
        :param subpath: Дочерний путь
        :return: Относительный путь или None, если subpath не находится в path
        """
        try:
            path = Path(path)
            subpath = Path(subpath)
            try:
                rel_path = subpath.relative_to(path)
                return str(rel_path)
            except ValueError:
                return None
        except Exception as e:
            logger.exception(f"Ошибка при вычислении относительного пути для {subpath}: {e}")
            return None
