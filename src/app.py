import os
import threading
import traceback
from pathlib import Path

from pystray import Icon, Menu, MenuItem
from PIL import Image

from src import APP_NAME, SETTINGS_PATH
from src.models.settings_model import Settings
from src.services.database_service import DatabaseService
from src.services.file_monitor_service import FileMonitorService
from src.services.synchronization_service import SynchronizationService
from src.utils.file_utils import FileUtils
from src.utils.logger_config import get_logger, log_exception
from src.utils.error_window import show_error
from src.components.settings_window import open_settings_window

logger = get_logger("app")

try:
    import locale

    locale.setlocale(locale.LC_ALL, 'Russian_Russia.1251')  # Для Windows
except locale.Error:
    logger.error("Не удалось установить русскую локаль. Возможно, она не установлена в вашей системе.")


class GeoOfficeSyncService:
    """Класс приложения для трея."""

    def __init__(self):
        self.is_running = False
        self._sync_thread = None
        self._stop_event = threading.Event()

        # Загружаем сохранённые настройки (если есть)
        self.settings = Settings(data=None)
        self._load_settings()

        # Инициализация базы данных
        self.database_service = DatabaseService(
            Path(self.settings.paths.file_server) / self.settings.paths.database_path)
        self.database_service.connection()

        # Инициализация сервиса мониторинга файлов
        self.file_monitor_service = FileMonitorService(self.database_service, self.settings.paths.file_server)

        # Инициализация сервиса синхронизации
        self.synchronization_service = SynchronizationService(self.database_service, self.settings.paths.file_server)

        # Создаем иконку
        self.icon = Icon(
            name=APP_NAME,
            title=f'{APP_NAME} Мониторинг остановлен',
            icon=self._get_icon(),
            menu=self._create_menu()
        )

    @log_exception
    def _load_settings(self) -> None:
        """Чтение настроек приложения"""
        logger.debug("Чтение настроек приложения")
        settings_data = FileUtils.load_json(SETTINGS_PATH)
        if settings_data is not None:
            try:
                self.settings = Settings(data=settings_data)
                logger.info("Настройки загружены успешно")
            except Warning as e:
                logger.warning(e)
        else:
            logger.info("Создание настроек по умолчанию")
            self._save_settings()

    @log_exception
    def _save_settings(self):
        """Сохранение настроек приложения"""
        logger.debug("Сохранение настроек приложения")
        if FileUtils.save_json(self.settings.to_dict(), SETTINGS_PATH):
            logger.info("Настройки успешно сохранены")
        else:
            logger.error("Ошибка сохранения настроек")

    @log_exception
    def _update_settings(self, server_path: str, database_path: str):
        """
        Обновление настроек из окна настроек.
        
        Args:
            server_path: Путь к файловому серверу
            database_path: Путь к базе данных
        """
        self.settings.paths.file_server = server_path
        self.settings.paths.database_path = database_path
        self._save_settings()
        
        # Переинициализируем сервис базы данных с новым путем
        self.database_service = DatabaseService(
            Path(self.settings.paths.file_server) / self.settings.paths.database_path)
        self.database_service.connection()
        
        # Переинициализируем сервис синхронизации с новыми настройками
        self.synchronization_service = SynchronizationService(self.database_service, self.settings.paths.file_server)
        
        # Переинициализируем сервис мониторинга файлов с новыми настройками
        self.file_monitor_service = FileMonitorService(self.database_service, self.settings.paths.file_server)

    @log_exception
    def _get_icon(self) -> Image:
        try:
            return Image.open("src/assets/icon.png")
        except Exception as e:
            logger.error(e)
            return Image.new('RGB', (64, 64), '#ffffff')

    @log_exception
    def _create_menu(self):
        return (
            MenuItem('Запустить мониторинг', self.start_action, enabled=not self.is_running),
            MenuItem('Остановить мониторинг', self.stop_action, enabled=self.is_running),
            MenuItem('Настройки', self.settings_action),
            MenuItem('Выход', self.exit_action),
        )

    @log_exception
    def _update_menu(self):
        self.icon.menu = Menu(*self._create_menu())
        self.icon.update_menu()

    @log_exception
    def _update_title(self):
        """Обновление заголовка иконки в зависимости от состояния мониторинга"""
        if self.is_running:
            self.icon.title = f'{APP_NAME} Мониторинг запущен'
        else:
            self.icon.title = f'{APP_NAME} Мониторинг остановлен'

    def start_action(self, icon, menu_item):
        """Запуск мониторинга файлов"""
        try:
            if not self.is_running:
                logger.info("Запуск мониторинга файлов...")
                if self.file_monitor_service.start_monitoring():
                    self.is_running = True
                    self._update_title()
                    self._update_menu()
                    logger.info("Мониторинг файлов успешно запущен")
                else:
                    logger.error("Ошибка при запуске мониторинга файлов")
                    show_error("Ошибка при запуске мониторинга файлов")
            else:
                logger.info("Мониторинг файлов уже запущен")
        except Exception as e:
            logger.exception(f"Ошибка при запуске мониторинга файлов:\n{traceback.format_exc()}")
            show_error(f"Ошибка при запуске мониторинга файлов:\n{traceback.format_exc()}")

    def stop_action(self, icon, menu_item):
        """Остановка мониторинга файлов"""
        try:
            if self.is_running:
                logger.info("Остановка мониторинга файлов...")
                if self.file_monitor_service.stop_monitoring():
                    self.is_running = False
                    self._update_title()
                    self._update_menu()
                    logger.info("Мониторинг файлов успешно остановлен")
                else:
                    logger.error("Ошибка при остановке мониторинга файлов")
                    show_error("Ошибка при остановке мониторинга файлов")
            else:
                logger.info("Мониторинг файлов не запущен")
        except Exception as e:
            logger.exception(f"Ошибка при остановке мониторинга файлов:\n{traceback.format_exc()}")
            show_error(f"Ошибка при остановке мониторинга файлов:\n{traceback.format_exc()}")

    def synchronization(self, icon, menu_item):
        """Запускает синхронизацию данных между БД и файловой системой"""
        try:
            self.synchronization_service.start_synchronization()
        except Exception as e:
            logger.exception(f"Ошибка при синхронизации данных:\n{traceback.format_exc()}")
            show_error(f"Ошибка при синхронизации данных:\n{traceback.format_exc()}")

    def settings_action(self, icon, menu_item):
        """Открывает окно настроек."""
        try:
            open_settings_window(
                server_path=self.settings.paths.file_server,
                database_path=self.settings.paths.database_path,
                on_save=self._update_settings
            )
        except Exception as e:
            logger.exception("Ошибка при открытии окна настроек")
            show_error(f"Ошибка при открытии окна настроек:\n{traceback.format_exc()}")

    def exit_action(self, icon, menu_item):
        try:
            logger.info("Выход из приложения...")
            self._stop_event.set()
            
            # Останавливаем мониторинг файлов при выходе
            if self.is_running:
                logger.info("Остановка мониторинга файлов перед выходом...")
                self.file_monitor_service.stop_monitoring()
            
            self.icon.stop()
        except Exception as e:
            logger.exception(f"Ошибка при выходе из приложения:\n{traceback.format_exc()}")
            show_error(f"Ошибка при выходе из приложения:\n{traceback.format_exc()}")

    @log_exception
    def run(self, detached: bool = True):
        try:
            if detached:
                self.icon.run_detached()
            else:
                self.icon.run()

            # Выполнение синхронизации после простоя
            # self.synchronization(None, None)

            self.start_action(None, None)

        except Exception as e:
            error = f"Ошибка при запуске приложения:\n{traceback.format_exc()}"
            logger.exception(error)
            show_error(error)