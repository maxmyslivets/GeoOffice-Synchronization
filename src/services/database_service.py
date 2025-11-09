import traceback
from pathlib import Path
from typing import Any
from datetime import datetime

from pony.orm import Database as PonyDatabase
from pony.orm import db_session, desc, select

from src.models.database_model import Database
from src.utils.logger_config import log_exception, get_logger

logger = get_logger("services.database_service")


class DatabaseService:
    """
    Сервис для работы с базой данных проектов.
    Содержит методы для работы с таблицами, определенными в DataBaseProjects.
    """
    @log_exception
    def __init__(self, path: Path | str) -> None:
        """
        Инициализация сервиса базы данных.
        :param path: Путь к файлу базы данных
        """
        self._path = Path(path)
        self.db: PonyDatabase | None = None
        self.models: Any = None
        self.connected = False

    @log_exception
    @db_session
    def connection(self) -> None:
        logger.debug(f"Инициализация базы данных: {self._path}")
        self.db = PonyDatabase()
        self.db.bind(provider='sqlite', filename=str(self._path))
        # Инициализация моделей
        self.models = Database(self.db).models
        # Генерируем схемы таблиц
        self.db.generate_mapping(check_tables=True)
        self.connected = True
        logger.info("База данных успешно инициализирована")

    @log_exception
    @db_session
    def create_project(self, name: str, path: str, uid: str, number: str = None, customer: str = None,
                       chief_engineer: str = None, chief_architect: str = None, head_of_the_sanitary: str = None,
                       address: str = None) -> Any:
        """
        Создание нового проекта.
        :param name: Название проекта
        :type name: str
        :param path: Путь к папке проекта
        :type path: str
        :param uid: Уникальный идентификатор
        :type uid: str
        :param number: Номер проекта
        :type number: str
        :param customer: Заказчик
        :type customer: str
        :param chief_engineer: Главный инженер
        :type chief_engineer: str
        :param chief_architect: Главный архитектор
        :type chief_architect: str
        :param head_of_the_sanitary: Начальник санитарно-технического отдела
        :type head_of_the_sanitary: str
        :param address: Адрес объекта
        :type address: str
        :return: Созданный проект
        :rtype: Any
        """
        logger.debug(f"Добавление проекта в БД: path=`{path}` uid=`{uid}` name=`{name}`")
        project = self.models.Project(
            number=number,
            name=name,
            customer=customer,
            chief_engineer=chief_engineer,
            chief_architect=chief_architect,
            head_of_the_sanitary=head_of_the_sanitary,
            address=address,
            path=path,
            uid=uid,
        )
        logger.debug(f"Проект успешно добавлен в БД: path=`{path}` uid=`{uid}` name=`{name}`")
        return project

    @log_exception
    @db_session
    def get_projects_from_path(self, path: str | Path) -> list[Any] | None:
        """
        Получение списка проектов с совпадающим путем.
        :param path: Путь относительно папки проектов
        :return: Список проектов (объекты БД)
        """
        logger.debug(f"Получение списка проектов по пути: path={path}")
        try:
            path = str(path)
            return self.models.Project.select_by_sql("SELECT * FROM Объекты WHERE path = $path")[:]
        except Exception:
            logger.error(f"Ошибка получения списка проектов по пути path=`{path}`: {traceback.format_exc()}")

    @log_exception
    @db_session
    def get_all_projects(self) -> list[Any]:
        logger.debug(f"Получение всех проектов")
        return self.models.Project.select()[:]

    @log_exception
    @db_session
    def get_project_from_uid(self, uid: str) -> Any:
        logger.debug(f"Получение проекта по уникальному идентификатору: uid={uid}")
        return self.models.Project.get(uid=uid)

    @log_exception
    @db_session
    def get_settings_project_dir(self) -> str:
        logger.debug(f"Получение пути расположения проектов")
        return self.models.Settings[1].project_dir

    @log_exception
    @db_session
    def get_settings_template_project_dir(self) -> str:
        logger.debug(f"Получение пути расположения шаблона проекта")
        return self.models.Settings[1].template_project_dir

    @log_exception
    @db_session
    def mark_deleted_project(self, project_id: int) -> None:
        """
        Помечает проект, как удаленный
        :param project_id: Индекс объекта проекта из БД
        """
        project = self.models.Project[project_id]
        project.status = "delete"
        project.modified_date = datetime.now()

    @log_exception
    @db_session
    def mark_active_project(self, project_id: int) -> None:
        """
        Помечает проект, как удаленный
        :param project_id: Индекс объекта проекта из БД
        """
        project = self.models.Project[project_id]
        project.status = "active"
        project.modified_date = datetime.now()

    @log_exception
    @db_session
    def update_project_path(self, project_id: int, new_rel_path: str | Path) -> None:
        """
        Обновляет путь проекта
        :param project_id: Индекс объекта проекта из БД
        :param new_rel_path: Новый путь относительно папки проектов
        """
        project = self.models.Project[project_id]
        project.path = str(new_rel_path)
        project.modified_date = datetime.now()

    @log_exception
    @db_session
    def update_project_modified_date(self, project_id: int) -> None:
        """
        Обновляет время изменения проекта
        :param project_id: Индекс объекта проекта из БД
        """
        project = self.models.Project[project_id]
        project.modified_date = datetime.now()

    @log_exception
    @db_session
    def update_project_name(self, project_id: int, name: str) -> None:
        """
        Обновляет название проекта
        :param project_id: Индекс объекта проекта из БД
        :param name: Название проекта
        """
        project = self.models.Project[project_id]
        project.name = name
        project.modified_date = datetime.now()
