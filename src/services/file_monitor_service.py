"""
Сервис мониторинга файлов проектов GeoOffice.

Отслеживает изменения в файлах .geo_office_project и реагирует на события:
- создание, изменение, удаление файлов проектов
- удаление директорий
- перемещение файлов проектов
"""
import traceback
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Event, Thread

from src.utils.file_utils import FileUtils
from src.utils.logger_config import get_logger, log_exception
from src.services.database_service import DatabaseService
from src.services.synchronization_service import SynchronizationService
from src.utils.project_file_utils import ProjectFileUtils
from src import PROJECT_FILE_NAME


logger = get_logger(__name__)


class FileMonitorService:
    """
    Сервис мониторинга файлов проектов GeoOffice.
    
    Использует watchdog для отслеживания изменений в файловой системе
    и реагирования на события, связанные с файлами проектов.
    """
    
    def __init__(self, synchronization_service: SynchronizationService, database_service: DatabaseService,
                 server_path: Path|str) -> None:
        """
        Инициализация сервиса мониторинга файлов.
        
        Args:
            synchronization_service: Сервис для синхронизации данных между базой данных и файловой системой
            database_service: Сервис для работы с базой данных
            server_path: Путь к файловому серверу
        """
        self.synchronization_service = synchronization_service
        self.database_service = database_service
        self.project_dir_path = Path(server_path) / self.database_service.get_settings_project_dir()
        self.template_exc_path = self.project_dir_path / self.database_service.get_settings_template_project_dir()
        
        # Наблюдатель за файловой системой
        self.observer: Optional[Observer] = None
        self.monitored_path: Optional[Path] = None
        self.is_monitoring = False
        
        # События для управления мониторингом
        self._stop_event = Event()
        self._monitoring_thread: Optional[Thread] = None
        
        # Обработчик файловых событий
        self.file_handler: Optional['ProjectFileHandler'] = None

    @log_exception
    def start_monitoring(self) -> bool:
        """
        Запуск мониторинга файлов проектов.
        
        Returns:
            bool: True если мониторинг успешно запущен, False иначе
        """
        try:
            if self.is_monitoring:
                logger.info("Мониторинг файлов уже запущен")
                return True
            
            # Получение пути для мониторинга из базы данных
            self.monitored_path = self._get_monitored_path()
            if not self.monitored_path:
                logger.error("Не удалось получить путь для мониторинга из базы данных")
                return False
            
            if not self.monitored_path.exists():
                logger.warning(f"Путь для мониторинга не существует: {self.monitored_path}")
                return False
            
            # Настройка наблюдателя
            if not self._setup_observer():
                return False
            
            # Запуск мониторинга в отдельном потоке
            self._monitoring_thread = Thread(target=self._monitoring_loop, daemon=True)
            self._monitoring_thread.start()
            
            self.is_monitoring = True
            logger.info(f"Мониторинг файлов запущен для пути: {self.monitored_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при запуске мониторинга файлов: {e}")
            return False

    @log_exception
    def stop_monitoring(self) -> bool:
        """
        Остановка мониторинга файлов.
        
        Returns:
            bool: True если мониторинг успешно остановлен, False иначе
        """
        try:
            if not self.is_monitoring:
                logger.info("Мониторинг файлов не запущен")
                return True
            
            # Устанавливаем событие остановки
            self._stop_event.set()
            
            # Останавливаем наблюдателя
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=5)
                if self.observer.is_alive():
                    logger.warning("Наблюдатель не остановился в течение таймаута")
                else:
                    logger.info("Наблюдатель успешно остановлен")
            
            # Ожидаем завершения потока мониторинга
            if self._monitoring_thread and self._monitoring_thread.is_alive():
                self._monitoring_thread.join(timeout=3)
                if self._monitoring_thread.is_alive():
                    logger.warning("Поток мониторинга не завершился в течение таймаута")
            
            # Очистка ресурсов
            self._cleanup()
            
            self.is_monitoring = False
            logger.info("Мониторинг файлов остановлен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при остановке мониторинга файлов: {e}")
            return False

    @log_exception
    def _get_monitored_path(self) -> Optional[Path]:
        """
        Получение пути для мониторинга из базы данных.
        
        Returns:
            Optional[Path]: Путь для мониторинга или None если не найден
        """
        try:
            if self.project_dir_path:
                return self.project_dir_path
            else:
                logger.error(f"Путь для мониторинга не получен.")
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении пути для мониторинга: {e}")
            return None

    @log_exception
    def _setup_observer(self) -> bool:
        """
        Настройка наблюдателя за файловой системой.
        
        Returns:
            bool: True если настройка успешна, False иначе
        """
        try:
            if not self.monitored_path:
                logger.error("Путь для мониторинга не установлен")
                return False
            
            # Создаем наблюдателя
            self.observer = Observer()
            
            # Создаем обработчик файловых событий
            self.file_handler = ProjectFileHandler(service=self)
            
            # Добавляем наблюдение за директорией
            self.observer.schedule(
                self.file_handler,
                str(self.monitored_path),
                recursive=True  # Включаем рекурсивный мониторинг поддиректорий
            )
            
            # Запускаем наблюдателя
            self.observer.start()
            
            logger.info(f"Наблюдатель настроен для пути: {self.monitored_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при настройке наблюдателя: {e}")
            return False

    @log_exception
    def _cleanup(self):
        """Очистка ресурсов."""
        try:
            if self.observer:
                self.observer = None
            if self.file_handler:
                self.file_handler = None
            self.monitored_path = None
            self._monitoring_thread = None
            
        except Exception as e:
            logger.error(f"Ошибка при очистке ресурсов: {e}")

    @log_exception
    def _monitoring_loop(self):
        """Основной цикл мониторинга в отдельном потоке."""
        try:
            logger.info("Запущен цикл мониторинга файлов")
            
            while not self._stop_event.is_set():
                # Проверяем состояние наблюдателя
                if self.observer and not self.observer.is_alive():
                    logger.warning("Наблюдатель остановился, перезапуск...")
                    try:
                        self.observer.join(timeout=1)
                        if not self._stop_event.is_set():
                            self._setup_observer()
                    except Exception as e:
                        logger.error(f"Ошибка при перезапуске наблюдателя: {e}")
                        break
                
                # Небольшая задержка для снижения нагрузки на CPU
                self._stop_event.wait(timeout=1)
            
            logger.info("Цикл мониторинга файлов завершен")
            
        except Exception as e:
            logger.error(f"Критическая ошибка в цикле мониторинга: {e}")
        finally:
            self.is_monitoring = False

    @log_exception
    def handle_created(self, file_path: Path) -> None:
        """
        Обработка события создания файла проекта.
        
        Args:
            file_path: Путь к созданному файлу проекта
        """
        try:
            if FileUtils.get_relative_path(self.template_exc_path, file_path):
                return
            if file_path.name == PROJECT_FILE_NAME:
                logger.info(f"Обработка события создания: `{file_path}`")
                self.synchronization_service.synchronize()
        except Exception:
            logger.error(f"Ошибка при обработке создания `{file_path}`: {traceback.format_exc()}")

    @log_exception
    def handle_modified(self, file_path: Path) -> None:
        """
        Обработка события изменения файла в папке проекта.

        Args:
            file_path: Путь к файлу в папке проекта
        """
        try:
            if FileUtils.get_relative_path(self.template_exc_path, file_path):
                return
            rel_path = FileUtils.get_relative_path(self.project_dir_path, file_path)
            projects = self.database_service.get_projects_from_path(rel_path)
            if projects:
                for project in projects:
                    logger.debug(f"Обработка события изменения: `{file_path}`")
                    self.database_service.update_project_modified_date(project.id)
        except Exception:
            logger.error(f"Ошибка при обработке изменения файла в папке проекта `{file_path}`: "
                         f"{traceback.format_exc()}")

    @log_exception
    def handle_moved(self, old_path: Path, new_path: Path) -> None:
        """
        Обработка события перемещения файла проекта.
        
        Args:
            old_path: Старый путь к файлу проекта
            new_path: Новый путь к файлу проекта
        """
        try:
            if (FileUtils.get_relative_path(self.template_exc_path, old_path) and
                FileUtils.get_relative_path(self.template_exc_path, new_path)):
                return
            if (old_path.name == PROJECT_FILE_NAME) or (new_path.name == PROJECT_FILE_NAME):
                logger.debug(f"Обработка события перемещения: `{old_path}` -> `{new_path}`")
                self.synchronization_service.synchronize()
        except Exception:
            logger.error(f"Ошибка при обработке перемещения файла проекта `{old_path}` -> `{new_path}`: "
                         f"{traceback.format_exc()}")

    @log_exception
    def handle_deleted(self, path: Path) -> None:
        """
        Обработка события удаления файла проекта.
        
        Args:
            path: Путь к удаленному файлу проекта
        """
        try:
            if FileUtils.get_relative_path(self.template_exc_path, path):
                return
            if path.name == PROJECT_FILE_NAME:
                logger.debug(f"Обработка события удаления: `{path}`")
                self.synchronization_service.synchronize()
            else:
                # если внутри директории есть папки проектов
                # либо сама директория является папкой проекта
                rel_path = FileUtils.get_relative_path(self.project_dir_path, path)
                for project in self.database_service.get_all_projects():
                    if rel_path in project.path:
                        logger.debug(f"Обработка события удаления: `{path}`")
                        self.synchronization_service.synchronize()
                        break
        except Exception:
            logger.error(f"Ошибка при обработке удаления файла или папки `{path}`: {traceback.format_exc()}")


class ProjectFileHandler(FileSystemEventHandler):
    """
    Обработчик файловых событий для файлов проектов GeoOffice.
    
    Перехватывает события файловой системы и делегирует обработку
    соответствующим методам FileMonitorService.
    """
    
    def __init__(self, service: 'FileMonitorService'):
        """
        Инициализация обработчика файловых событий.
        
        Args:
            service: Сервис мониторинга файлов
        """
        self.service = service
        super().__init__()

    @log_exception
    def on_created(self, event):
        """Обработка события создания файла или директории."""
        logger.debug(f"Событие создания: `{event.src_path}`")
        if not event.is_directory:
            self.service.handle_created(Path(event.src_path))

    @log_exception
    def on_modified(self, event):
        """Обработка события изменения файла."""
        logger.debug(f"Событие изменения: `{event.src_path}`")
        self.service.handle_modified(Path(event.src_path))

    @log_exception
    def on_deleted(self, event):
        """Обработка события удаления файла или директории."""
        logger.debug(f"Событие удаления: `{event.src_path}`")
        self.service.handle_deleted(Path(event.src_path))

    @log_exception
    def on_moved(self, event):
        """Обработка события перемещения или переименования файла."""
        logger.debug(f"Событие перемещения: `{event.src_path}` -> `{event.dest_path}`")
        old_path = Path(event.src_path)
        new_path = Path(event.dest_path)
        self.service.handle_moved(old_path, new_path)