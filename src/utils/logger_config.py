"""
Модуль для настройки логирования приложения GeoOffice
"""
import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from src import APP_NAME

# Добавляем colorama для цветов
try:
    import colorama
    from colorama import Fore, Style
    colorama.init()
    COLORS_AVAILABLE = True
except ImportError:
    COLORS_AVAILABLE = False
    Fore = Style = None


class ColoredFormatter(logging.Formatter):
    """Форматтер с цветами для консоли"""

    # Цвета для разных уровней
    COLORS = {
        'DEBUG': Fore.CYAN + Style.DIM if COLORS_AVAILABLE else '',
        'INFO': Fore.GREEN if COLORS_AVAILABLE else '',
        'WARNING': Fore.YELLOW + Style.BRIGHT if COLORS_AVAILABLE else '',
        'ERROR': Fore.RED + Style.BRIGHT if COLORS_AVAILABLE else '',
        'CRITICAL': Fore.RED + Style.BRIGHT + Fore.WHITE if COLORS_AVAILABLE else '',
    }

    def format(self, record):
        # Получаем цвет для уровня
        color = self.COLORS.get(record.levelname, '')
        reset = Style.RESET_ALL if COLORS_AVAILABLE else ''

        # Форматируем сообщение
        formatted = super().format(record)

        # Добавляем цвет и эмодзи
        return f"{color}{formatted}{reset}"


class GeoOfficeLogger:
    """
    Класс для настройки логирования приложения GeoOffice.
    Позволяет настраивать форматтеры, обработчики, логгеры для модулей и получать логгер для нужного модуля.
    """
    
    def __init__(self, app_name=APP_NAME):
        self.app_name = app_name
        self.log_dir = Path(os.path.expanduser("~/Documents")) / APP_NAME / "logs"
        self.log_dir.mkdir(exist_ok=True)
        
        # Создаем основной логгер приложения
        self.logger = logging.getLogger(app_name)
        self.logger.setLevel(logging.DEBUG)
        
        # Очищаем существующие обработчики
        self.logger.handlers.clear()
        
        # Настраиваем форматирование
        self.setup_formatters()
        
        # Настраиваем обработчики
        self.setup_handlers()
        
        # Настраиваем логгеры для модулей
        self.setup_module_loggers()

    def setup_formatters(self):
        """
        Настройка форматирования логов для файлов, консоли и пользовательского интерфейса.
        """
        # Подробный форматтер для файлов
        self.detailed_formatter = logging.Formatter(
            fmt='%(asctime)s | %(name)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(funcName)s() | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Цветной форматтер для консоли
        self.simple_formatter = ColoredFormatter(
            fmt='%(name)s | %(levelname)-8s | %(funcName)s() | %(message)s'
        )

        # Красивый форматтер для пользовательского интерфейса
        self.ui_formatter = logging.Formatter(
            fmt='[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
    
    def setup_handlers(self):
        """
        Настройка обработчиков логов: консоль, файлы, ошибки, ежедневные логи.
        """
        
        # 1. Обработчик для консоли (INFO и выше)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)     # Устанавливаем уровень для консоли (по умолчанию INFO)
        console_handler.setFormatter(self.simple_formatter)
        self.logger.addHandler(console_handler)
        
        # 2. Обработчик для основного файла логов (DEBUG и выше)
        main_log_file = self.log_dir / f"{self.app_name.lower()}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            main_log_file,
            maxBytes=10*1024*1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(self.detailed_formatter)
        self.logger.addHandler(file_handler)
        
        # 3. Обработчик для ошибок (ERROR и выше)
        error_log_file = self.log_dir / f"{self.app_name.lower()}_errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(self.detailed_formatter)
        self.logger.addHandler(error_handler)
        
        # 4. Обработчик для ежедневных логов
        daily_log_file = self.log_dir / f"{self.app_name.lower()}_{datetime.now().strftime('%Y%m%d')}.log"
        daily_handler = logging.handlers.TimedRotatingFileHandler(
            daily_log_file,
            when='midnight',
            interval=1,
            backupCount=30,  # Хранить 30 дней
            encoding='utf-8'
        )
        daily_handler.setLevel(logging.INFO)
        daily_handler.setFormatter(self.detailed_formatter)
        self.logger.addHandler(daily_handler)
    
    def setup_module_loggers(self):
        """
        Настройка логгеров для различных модулей приложения (pages, services, utils, models, files, data).
        """

        # Логгер для страниц
        pages_logger = logging.getLogger(f"{self.app_name}.pages")
        pages_logger.setLevel(logging.DEBUG)
        
        # Логгер для сервисов
        services_logger = logging.getLogger(f"{self.app_name}.services")
        services_logger.setLevel(logging.DEBUG)
        
        # Логгер для утилит
        utils_logger = logging.getLogger(f"{self.app_name}.utils")
        utils_logger.setLevel(logging.DEBUG)
        
        # Логгер для моделей
        models_logger = logging.getLogger(f"{self.app_name}.models")
        models_logger.setLevel(logging.DEBUG)
        
        # Логгер для файловых операций
        file_logger = logging.getLogger(f"{self.app_name}.files")
        file_logger.setLevel(logging.DEBUG)
        
        # Логгер для операций с данными
        data_logger = logging.getLogger(f"{self.app_name}.data")
        data_logger.setLevel(logging.DEBUG)
    
    def get_logger(self, module_name=None):
        """
        Получить логгер для конкретного модуля.
        :param module_name: Имя модуля (например, 'pages')
        :return: Логгер logging.Logger
        """
        if module_name:
            return logging.getLogger(f"{self.app_name}.{module_name}")
        return self.logger
    
    def log_startup(self):
        """
        Логирование запуска приложения (выводит информацию о запуске).
        """
        self.logger.info("=" * 60)
        self.logger.info(f"Запуск приложения {self.app_name}")
        self.logger.info(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Версия Python: {sys.version}")
        self.logger.info(f"Рабочая директория: {os.getcwd()}")
        self.logger.info(f"Директория логов: {self.log_dir.absolute()}")
        self.logger.info("=" * 60)
    
    def log_shutdown(self):
        """
        Логирование завершения приложения (выводит информацию о завершении).
        """
        self.logger.info("=" * 60)
        self.logger.info(f"Завершение приложения {self.app_name}")
        self.logger.info(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)


# Глобальный экземпляр логгера
_app_logger = None


def setup_logging(app_name="GeoOffice"):
    """
    Настройка глобального логгера приложения.
    :param app_name: Имя приложения
    :return: Экземпляр GeoOfficeLogger
    """
    global _app_logger
    _app_logger = GeoOfficeLogger(app_name)
    _app_logger.log_startup()
    return _app_logger


def get_logger(module_name=None):
    """
    Получить логгер для указанного модуля.
    :param module_name: Имя модуля
    :return: Логгер logging.Logger
    """
    global _app_logger
    if _app_logger is None:
        setup_logging()
    return _app_logger.get_logger(module_name)


def log_function_call(func):
    """
    Декоратор для логирования вызовов функций.
    :param func: Функция для обёртывания
    :return: Обёрнутая функция
    """
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        logger.debug(f"Вызов функции: {func.__name__}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"Функция {func.__name__} выполнена успешно")
            return result
        except Exception as e:
            logger.error(f"Ошибка в функции {func.__name__}: {str(e)}")
            raise
    return wrapper


def log_exception(func):
    """
    Декоратор для логирования исключений в функции.
    :param func: Функция для обёртывания
    :return: Обёрнутая функция
    """
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Исключение в {func.__name__}: {str(e)}")
            raise
    return wrapper
