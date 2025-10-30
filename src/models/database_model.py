from datetime import datetime
from typing import Any

from pony.orm import Database as PonyDatabase
from pony.orm import PrimaryKey, Required, Optional, Set, db_session, select


class Database:
    def __init__(self, db: PonyDatabase):
        """
        Инициализация моделей базы данных.
        :param db: Экземпляр базы данных Pony ORM
        """
        self.db = db
        self.models = self._define_models()

    def _define_models(self) -> Any:
        """Определение моделей таблиц базы данных"""
        class ProjectTable(self.db.Entity):
            """
            Модель таблицы проектов.
            Основная таблица для хранения информации о проектах.
            """
            _table_ = "Объекты"
            id = PrimaryKey(int, auto=True)
            number = Optional(str, nullable=True, default=None)  # Номер проекта
            name = Required(str)  # Название проекта
            customer = Optional(str, nullable=True, default=None)  # Заказчик
            chief_engineer = Optional(str, nullable=True, default=None)  # Главный инженер проекта
            chief_architect = Optional(str, nullable=True, default=None)  # Главный архитектор проекта
            head_of_the_sanitary = Optional(str, nullable=True, default=None)  # Начальник санитарно-технического отдела
            status = Optional(str, nullable=True, default="active")  # Статус проекта (active, completed, archived)
            address = Optional(str, nullable=True, default=None)  # Адрес объекта
            path = Required(str)    # Путь к папке проекта
            uid = Required(str)     # Уникальный идентификатор
            created_date = Required(datetime, default=datetime.now)
            modified_date = Required(datetime, default=datetime.now)

            def __str__(self):
                return f"Project(id={self.id}, number='{self.number}', name='{self.name}')"

            @db_session
            def to_dict(self) -> dict:
                """Конвертация в словарь"""
                def datetime_format(dt: datetime | str) -> str:
                    if isinstance(dt, datetime):
                        dt_format = dt.isoformat()
                    else:
                        try:
                            if dt.count(':') == 3:
                                # Разделяем основную часть и миллисекунды
                                main_part, milliseconds = dt.rsplit(':', 1)
                                dt = datetime.strptime(main_part, '%d.%m.%Y %H:%M:%S')
                                dt_format = dt.replace(microsecond=int(milliseconds) * 1000).isoformat()
                            else:
                                dt_format = datetime.strptime(dt, '%d.%m.%Y %H:%M:%S').isoformat()
                        except Exception as e:
                            raise Exception(f"Ошибка получения объекта из базы данных:\n{e}")
                    return dt_format
                return {
                    'id': self.id,
                    'number': self.number,
                    'name': self.name,
                    'customer': self.customer,
                    'chief_engineer': self.chief_engineer,
                    'chief_architect': self.chief_architect,
                    'head_of_the_sanitary': self.head_of_the_sanitary,
                    'status': self.status,
                    'address': self.address,
                    'path': self.path,
                    'created_date': datetime_format(self.created_date),
                    'modified_date': datetime_format(self.modified_date),
                }

        class SettingsTable(self.db.Entity):
            """
            Модель таблицы настроек.
            """
            _table_ = "Настройки"
            id = PrimaryKey(int, auto=True)
            project_dir = Optional(str, nullable=False)     # путь к папке объектов относительно файлового сервера
            template_project_dir = Optional(str, nullable=False)  # путь к папке шаблона объектов относительно файлового сервера

        class Models:
            Project = ProjectTable
            Settings = SettingsTable

        return Models
