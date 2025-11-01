"""
Утилиты для работы с файлами проектов GeoOffice.
Содержит статические методы для обнаружения, анализа и управления файлами проектов.
"""
import json
import os
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
    def is_project_file(file_path: str | Path) -> bool:
        """
        Проверяет, является ли файл файлом проекта GeoOffice.
        
        :param file_path: Путь к файлу для проверки
        :return: True, если файл является файлом проекта, иначе False
        """
        path = Path(file_path)
        
        if not path.exists() or not path.is_file():
            return False
        
        # Проверяем, что имя файла соответствует константе PROJECT_FILE_NAME
        is_project = path.name == PROJECT_FILE_NAME
        return is_project

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
        uid = str(uuid.uuid4())
        try:
            with file_path.open("w", encoding="utf-8") as f:
                f.write(uid)
            logger.info(f"Записан новый UID `{uid}` в файл проекта: {file_path}")
            return uid
        except Exception as e:
            logger.error(f"Ошибка при записи UID в файл {file_path}: {e}")
            return None

    @staticmethod
    @log_exception
    def get_relative_project_path(project_dir_path: str | Path, file_path: str | Path) -> str | None:
        """
        Вычисляет относительный путь проекта от server_path + project_dir.
        Возвращает None, если путь не соответствует ожидаемой структуре.
        """
        try:
            project_dir_path = Path(project_dir_path)
            file_path = Path(file_path)
            try:
                rel_path = file_path.relative_to(project_dir_path)
                return str(rel_path)
            except ValueError:
                logger.warning(f"Путь {file_path} не находится внутри {project_dir_path}")
                return None
        except Exception as e:
            logger.exception(f"Ошибка при вычислении относительного пути для {file_path}: {e}")
            return None

    @staticmethod
    @log_exception
    def get_project_directory_from_file(file_path: str | Path) -> Optional[Path]:
        """
        Получает директорию проекта из пути к файлу проекта.
        
        :param file_path: Путь к файлу проекта
        :return: Директория проекта или None, если файл не является файлом проекта
        """
        path = Path(file_path)
        logger.debug(f"Получение директории проекта из файла: {path}")

        if not ProjectFileUtils.is_project_file(path):
            logger.warning(f"Файл не является файлом проекта: {path}")
            return None
        
        # Директория проекта - это родительская директория файла проекта
        project_dir = path.parent
        logger.info(f"Найдена директория проекта: {project_dir}")
        return project_dir
    
    @staticmethod
    @log_exception
    def scan_directory_for_project_files(directory: str | Path) -> List[Path]:
        """
        Сканирует директорию на наличие файлов проектов.
        
        :param directory: Директория для сканирования
        :return: Список путей к файлам проектов
        """
        dir_path = Path(directory)
        logger.debug(f"Сканирование директории на наличие файлов проектов: {dir_path}")
        
        if not dir_path.exists() or not dir_path.is_dir():
            logger.error(f"Директория не существует или не является директорией: {dir_path}")
            return []
        
        project_files = []
        
        try:
            # Ищем файлы с именем PROJECT_FILE_NAME в указанной директории
            for item in dir_path.iterdir():
                if item.is_file() and item.name == PROJECT_FILE_NAME:
                    project_files.append(item)
                    logger.debug(f"Найден файл проекта: {item}")
            
            logger.info(f"Найдено {len(project_files)} файлов проектов в директории {dir_path}")
            
        except Exception as e:
            logger.error(f"Ошибка при сканировании директории {dir_path}: {str(e)}")
            
        return project_files
    
    @staticmethod
    @log_exception
    def find_project_files_in_subdirectories(base_directory: str | Path, max_depth: int = 3) -> List[Path]:
        """
        Находит файлы проектов в поддиректориях.
        
        :param base_directory: Базовая директория для поиска
        :param max_depth: Максимальная глубина поиска (по умолчанию 3)
        :return: Список путей к найденным файлам проектов
        """
        base_dir = Path(base_directory)
        logger.debug(f"Поиск файлов проектов в поддиректориях. База: {base_dir}, глубина: {max_depth}")
        
        if not base_dir.exists() or not base_dir.is_dir():
            logger.error(f"Базовая директория не существует или не является директорией: {base_dir}")
            return []
        
        project_files = []
        
        try:
            # Рекурсивно ищем файлы проектов
            for root, dirs, files in os.walk(base_dir):
                root_path = Path(root)
                
                # Вычисляем текущую глубину относительно базовой директории
                current_depth = len(root_path.relative_to(base_dir).parts)
                
                if current_depth > max_depth:
                    # Прекращаем углубление в эту ветку
                    dirs.clear()
                    continue
                
                logger.debug(f"Сканирование директории: {root_path} (глубина: {current_depth})")
                
                # Ищем файлы проектов в текущей директории
                for file in files:
                    if file == PROJECT_FILE_NAME:
                        project_file_path = root_path / file
                        project_files.append(project_file_path)
                        logger.debug(f"Найден файл проекта: {project_file_path}")
            
            logger.info(f"Найдено {len(project_files)} файлов проектов в поддиректориях {base_dir}")
            
        except Exception as e:
            logger.error(f"Ошибка при поиске файлов проектов в {base_dir}: {str(e)}")
            
        return project_files
    
    @staticmethod
    @log_exception
    def get_project_info_from_file(project_file_path: str | Path) -> Dict[str, Any]:
        """
        Получает информацию о проекте из файла проекта.
        
        :param project_file_path: Путь к файлу проекта
        :return: Словарь с информацией о проекте
        """
        path = Path(project_file_path)
        logger.debug(f"Получение информации о проекте из файла: {path}")
        
        project_info = {
            "file_path": str(path),
            "directory": str(path.parent),
            "name": path.parent.name,
            "exists": path.exists(),
            "last_modified": None,
            "size": 0,
            "data": {},
            "error": None
        }
        
        # Всегда проверяем, является ли файл файлом проекта, даже если он не существует
        if not ProjectFileUtils.is_project_file(path):
            logger.error(f"Файл не является файлом проекта: {path}")
            project_info["error"] = "Файл не является файлом проекта"
            return project_info
        
        try:
            if path.exists() and path.is_file():
                # Получаем метаданные файла
                stat = path.stat()
                project_info["last_modified"] = stat.st_mtime
                project_info["size"] = stat.st_size
                
                # Пытаемся загрузить данные из файла как JSON
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        project_info["data"] = data
                        logger.debug(f"Успешно загружены данные проекта из {path}")
                except json.JSONDecodeError:
                    # Файл не является валидным JSON
                    logger.warning(f"Файл проекта {path} не содержит валидный JSON")
                    project_info["error"] = "Файл не содержит валидный JSON"
                except Exception as e:
                    logger.error(f"Ошибка чтения файла проекта {path}: {str(e)}")
                    project_info["error"] = f"Ошибка чтения файла: {str(e)}"
            else:
                project_info["error"] = "Файл не существует"
                logger.warning(f"Файл проекта не существует: {path}")
                
        except Exception as e:
            logger.error(f"Ошибка получения информации о проекте {path}: {str(e)}")
            project_info["error"] = str(e)
        
        logger.info(f"Информация о проекте получена: {path.parent.name}")
        return project_info
    
    @staticmethod
    @log_exception
    def is_project_directory(directory_path: str | Path) -> bool:
        """
        Проверяет, является ли директорией проекта GeoOffice.
        
        :param directory_path: Путь к директории для проверки
        :return: True, если директория является директорией проекта, иначе False
        """
        # FIXME: изменить. Проверка через сравнение части пути из бд
        path = Path(directory_path)
        logger.debug(f"Проверка директории проекта: {path}")
        
        if not path.exists() or not path.is_dir():
            logger.debug(f"Директория не существует или не является директорией: {path}")
            return False
        
        # Проверяем наличие файла проекта в директории
        project_file_path = path / PROJECT_FILE_NAME
        is_project = project_file_path.exists() and project_file_path.is_file()
        logger.debug(f"Директория {path} {'является' if is_project else 'не является'} директорией проекта")
        return is_project