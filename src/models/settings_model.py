from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class Paths:
    """
    Модель настроек путей.
    :param file_server: Путь к файловому серверу
    :param database_path: Путь к базе данных проектов (относительно файлового сервера)
    """
    file_server: str
    database_path: str


@dataclass
class Settings:
    """
    Модель настроек.
    :param data: Словарь настроек из JSON
    :param paths: Настройки путей
    """
    data: dict[str, Any] | None
    paths: Paths | None = None

    def __post_init__(self):
        """Автоматическая инициализация после создания объекта"""
        if self.data is None:
            self.init_default_settings()
        else:
            self.load()

    def load(self) -> None:
        """
        Инициализация настроек.
        """
        try:
            paths = Paths(**self.data['paths'])
            self.paths = paths
        except Exception as e:
            raise Warning(f"Не удалось загрузить настройки, используются настройки по умолчанию.\nОшибка:\n{e}")

    def to_dict(self) -> dict:
        """
        Конвертирует настройки в словарь, используя dataclasses.asdict().
        :return: Словарь настроек
        """
        return {
            'paths': asdict(self.paths),
        }

    def init_default_settings(self) -> None:
        """Инициализация настроек по умолчанию"""
        self.paths = Paths(
            file_server=r"\\server-r\IGI",
            database_path='\\geo_office.db'
        )
