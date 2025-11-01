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
        logger.info(f"Инициализация базы данных: {self._path}")
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
        logger.debug(f"Создан новый проект: {project}")
        return project

    @log_exception
    @db_session
    def update_project(self, project_model):
        project = self.get_project_from_id(project_model.id)
        project.number = project_model.number
        project.name = project_model.name
        project.path = project_model.path
        project.customer = project_model.customer
        project.chief_engineer = project_model.chief_engineer
        project.chief_architect = project_model.chief_architect
        project.head_of_the_sanitary = project_model.head_of_the_sanitary
        project.status = project_model.status
        project.address = project_model.address
        project.modified_date = datetime.now()
        return project

    @log_exception
    @db_session
    def get_project_from_id(self, project_id: int) -> Any:
        logger.debug(f"Получение проекта по id: id={project_id}")
        return self.models.Project[project_id]

    @log_exception
    @db_session
    def get_project_from_path(self, path: str | Path) -> Any:
        logger.debug(f"Получение проекта по пути: path={path}")
        return self.models.Project.select_by_sql("SELECT * FROM Объекты WHERE path = $path")[0]

    @log_exception
    @db_session
    def get_all_projects(self) -> list[Any]:
        logger.debug(f"Получение всех проектов")
        return self.models.Project.select()[:]

    @log_exception
    @db_session
    def search_project(self, query: str, sorted_from_modified_date: bool = False) -> list[Any]:
        """
        Поиск проектов по названию.
        :param query: Поисковой запрос
        :param sorted_from_modified_date: Сортировка по времени последнего редактирования
        :return: Список кортежей
        """
        query = query.lower()
        if sorted_from_modified_date:
            projects = self.models.Project.select().order_by(desc(self.models.Project.modified_date))[:]
        else:
            projects = self.models.Project.select()[:]
        results = []
        for project in projects:
            if query in f"{str(project.number).lower()} {project.name.lower()} {str(project.customer).lower()}":
                results.append((project.id, project.number, project.name, project.customer))
        return results

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
