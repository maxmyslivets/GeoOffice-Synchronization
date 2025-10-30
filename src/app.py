import os
import threading
import traceback
from pathlib import Path

from pystray import Icon, Menu, MenuItem
from PIL import Image

from src import APP_NAME, SETTINGS_PATH
from src.models.settings_model import Settings
from src.services.database_service import DatabaseService
from src.utils.file_utils import FileUtils
from src.utils.logger_config import get_logger, log_exception
from src.utils.error_window import show_error

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
        # self._sync_thread = None
        # self._stop_event = threading.Event()

        # Загружаем сохранённые настройки (если есть)
        self.settings = Settings(data=None)
        self._load_settings()

        # Инициализация базы данных
        self.database_service = DatabaseService(
            Path(self.settings.paths.file_server) / self.settings.paths.database_path)

        # self._init_observer()

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
    def _get_icon(self) -> Image:
        try:
            return Image.open("src/assets/icon.png")
        except Exception as e:
            logger.error(e)
            return Image.new('RGB', (64, 64), '#ffffff')

    @log_exception
    def _create_menu(self):
        return (
            # MenuItem('Запустить мониторинг', self.start_action, enabled=not self.is_running),
            # MenuItem('Остановить мониторинг', self.stop_action, enabled=self.is_running),
            # MenuItem('Синхронизировать', self.synchronization),
            # MenuItem('Настройки', self.settings_action),
            MenuItem('Выход', self.exit_action),
        )

    @log_exception
    def _update_menu(self):
        self.icon.menu = Menu(*self._create_menu())
        self.icon.update_menu()

    def exit_action(self, icon, menu_item):
        try:
            logger.info("Выход из приложения...")
            # self._stop_event.set()
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
        except Exception as e:
            error = f"Ошибка при запуске приложения:\n{traceback.format_exc()}"
            logger.exception(error)
            show_error(error)
