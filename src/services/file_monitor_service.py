"""
Сервис мониторинга файлов проектов GeoOffice.

Отслеживает изменения в файлах .geo_office_project и реагирует на события:
- создание, изменение, удаление файлов проектов
- удаление директорий
- перемещение файлов проектов
"""

from pathlib import Path
from typing import Optional, Dict, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Event, Thread
from src.utils.logger_config import get_logger, log_exception
from src.services.database_service import DatabaseService
from src.utils.project_file_utils import ProjectFileUtils


logger = get_logger(__name__)


class FileMonitorService:
    """
    Сервис мониторинга файлов проектов GeoOffice.
    
    Использует watchdog для отслеживания изменений в файловой системе
    и реагирования на события, связанные с файлами проектов.
    """
    
    def __init__(self, database_service: DatabaseService, server_path: Path|str) -> None:
        """
        Инициализация сервиса мониторинга файлов.
        
        Args:
            database_service: Сервис для работы с базой данных
            server_path: Путь к файловому серверу
        """
        self.database_service = database_service
        self.server_path = Path(server_path)
        
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
            # Получаем путь к папке проектов из базы данных
            projects_folder = self.server_path / self.database_service.get_settings_project_dir()
            if projects_folder:
                return Path(projects_folder)
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
    def handle_project_file_created(self, file_path: Path) -> None:
        """
        Обработка события создания файла проекта.
        
        Args:
            file_path: Путь к созданному файлу проекта
        """
        try:
            if ProjectFileUtils.is_project_file(file_path):
                logger.info(f"Обнаружен новый файл проекта: {file_path}")
                
                file_text = ProjectFileUtils.read_project_file(file_path)
                if ProjectFileUtils.is_uid(file_text):
                    uid = file_text
                else:
                    uid = ProjectFileUtils.set_uid(file_path)
                    if uid is None:
                        logger.error(f"UUID не добавлен в файл проекта `{file_path}`")
                        return
                if self.database_service.get_project_from_uid(uid):
                    return
                project_dir_path = self.server_path / self.database_service.get_settings_project_dir()
                rel_path = ProjectFileUtils.get_relative_project_path(project_dir_path, file_path)
                name = file_path.parent.name
                self.database_service.create_project(name, rel_path, uid)
        except Exception as e:
            logger.error(f"Ошибка при обработке создания файла проекта {file_path}: {e}")

    @log_exception
    def handle_project_file_moved(self, old_path: Path, new_path: Path) -> None:
        """
        Обработка события перемещения файла проекта.
        
        Args:
            old_path: Старый путь к файлу проекта
            new_path: Новый путь к файлу проекта
        """
        try:
            if (ProjectFileUtils.is_project_file(old_path) or 
                ProjectFileUtils.is_project_file(new_path)):
                
                logger.info(f"Файл проекта перемещен: {old_path} -> {new_path}")
                
                # Здесь можно добавить логику обработки:
                # - обновление пути в базе данных
                # - уведомление об изменении структуры проекта
                # - проверка целостности данных
                
                # Заглушка - в будущем здесь будет реализована логика
                logger.debug(f"Обработка перемещения файла проекта: {old_path} -> {new_path}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке перемещения файла проекта {old_path} -> {new_path}: {e}")

    @log_exception
    def handle_project_file_deleted(self, file_path: Path) -> None:
        """
        Обработка события удаления файла проекта.
        
        Args:
            file_path: Путь к удаленному файлу проекта
        """
        try:
            if ProjectFileUtils.is_project_file(file_path):
                logger.info(f"Файл проекта удален: {file_path}")
                
                # Здесь можно добавить логику обработки:
                # - удаление из базы данных
                # - очистка связанных данных
                # - уведомление пользователя
                # - создание резервной копии
                
                # Заглушка - в будущем здесь будет реализована логика
                logger.debug(f"Обработка удаления файла проекта: {file_path}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке удаления файла проекта {file_path}: {e}")

    @log_exception
    def handle_directory_deleted(self, dir_path: Path) -> None:
        """
        Обработка события удаления директории.
        
        Args:
            dir_path: Путь к удаленной директории
        """
        try:
            logger.info(f"Директория удалена: {dir_path}")
            
            # Проверяем, была ли удалена директория проекта
            if ProjectFileUtils.is_project_directory(dir_path):
                logger.warning(f"Удалена директория проекта: {dir_path}")
                
                # Здесь можно добавить логику обработки:
                # - поиск файлов проектов в удаленной директории
                # - удаление связанных данных из базы
                # - уведомление об удалении проекта
                
                # Заглушка - в будущем здесь будет реализована логика
                logger.debug(f"Обработка удаления директории проекта: {dir_path}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке удаления директории {dir_path}: {e}")


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
        try:
            if event.is_directory:
                logger.debug(f"Создана директория: {event.src_path}")
            else:
                file_path = Path(event.src_path)
                if ProjectFileUtils.is_project_file(file_path):
                    self.service.handle_project_file_created(file_path)
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке события создания {event.src_path}: {e}")

    @log_exception
    def on_modified(self, event):
        """Обработка события изменения файла."""
        try:
            if not event.is_directory:
                file_path = Path(event.src_path)
                if ProjectFileUtils.is_project_file(file_path):
                    logger.debug(f"Изменен файл проекта: {file_path}")
                    # При изменении файла проекта также вызываем обработчик создания
                    # для обновления состояния в системе
                    self.service.handle_project_file_created(file_path)
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке события изменения {event.src_path}: {e}")

    @log_exception
    def on_deleted(self, event):
        """Обработка события удаления файла или директории."""
        try:
            if event.is_directory:
                dir_path = Path(event.src_path)
                self.service.handle_directory_deleted(dir_path)
            else:
                file_path = Path(event.src_path)
                if ProjectFileUtils.is_project_file(file_path):
                    self.service.handle_project_file_deleted(file_path)
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке события удаления {event.src_path}: {e}")

    @log_exception
    def on_moved(self, event):
        """Обработка события перемещения или переименования файла."""
        try:
            if not event.is_directory:
                old_path = Path(event.src_path)
                new_path = Path(event.dest_path)
                
                if (ProjectFileUtils.is_project_file(old_path) or 
                    ProjectFileUtils.is_project_file(new_path)):
                    self.service.handle_project_file_moved(old_path, new_path)
            else:
                # Для директорий обрабатываем как удаление старой и создание новой
                old_dir_path = Path(event.src_path)
                new_dir_path = Path(event.dest_path)
                logger.debug(f"Директория перемещена: {old_dir_path} -> {new_dir_path}")
                
        except Exception as e:
            logger.error(f"Ошибка при обработке события перемещения {event.src_path} -> {event.dest_path}: {e}")