"""
Сервис синхронизации данных GeoOffice.

Обеспечивает синхронизацию между базой данных и файловой системой,
отслеживая изменения в проектах и поддерживая консистентность данных.
"""

import threading
import traceback
import uuid
from pathlib import Path
from typing import Dict, Optional, Any

from src.utils.logger_config import get_logger, log_exception
from src.utils.file_utils import FileUtils
from src.utils.project_file_utils import ProjectFileUtils
from src.services.database_service import DatabaseService
from src import PROJECT_FILE_NAME, APP_NAME

logger = get_logger("services.synchronization_service")


class SynchronizationService:
    """
    Сервис для синхронизации данных между базой данных и файловой системой.
    
    Отвечает за:
    - Сканирование файловой системы для обнаружения проектов
    - Синхронизацию UID между файлами и базой данных
    - Обработку конфликтов и несоответствий
    - Обновление статуса проектов
    """
    
    def __init__(self, database_service: DatabaseService, server_path: str | Path) -> None:
        """
        Инициализация сервиса синхронизации.
        
        Args:
            database_service: Сервис для работы с базой данных
            server_path: Путь к файловому серверу
        """
        self.database_service = database_service
        self.server_path = Path(server_path)
        self._sync_thread: Optional[threading.Thread] = None
        self._is_synchronizing = False
        
        # Пути к папкам проектов и шаблонов
        self.projects_root_path = self.server_path / self.database_service.get_settings_project_dir()
        self.template_exc_path = self.projects_root_path / self.database_service.get_settings_template_project_dir()
        
        logger.info(f"Инициализирован сервис синхронизации для пути: {self.projects_root_path}")

    @log_exception
    def start_synchronization(self) -> bool:
        """
        Запускает процесс синхронизации в фоновом потоке.
        
        Returns:
            bool: True если синхронизация успешно запущена, False иначе
        """
        try:
            if self._is_synchronizing:
                logger.warning("Синхронизация уже выполняется")
                return False
                
            if not self._validate_paths():
                return False
                
            # Запускаем синхронизацию в отдельном потоке
            self._sync_thread = threading.Thread(
                target=self._synchronization_process,
                name=APP_NAME,
                daemon=True
            )
            self._sync_thread.start()

            logger.debug("Запущена синхронизация")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при запуске синхронизации: {e}")
            return False

    @log_exception
    def _validate_paths(self) -> bool:
        """
        Проверяет корректность настроенных путей.
        
        Returns:
            bool: True если пути корректны, False иначе
        """
        try:
            if not self.server_path.exists():
                logger.error(f"Путь к файловому серверу не существует: {self.server_path}")
                return False
                
            if not self.projects_root_path.exists():
                logger.error(f"Папка проектов не существует: {self.projects_root_path}")
                return False
                
            logger.debug("Валидация путей прошла успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при валидации путей: {e}")
            return False

    @log_exception
    def _synchronization_process(self) -> None:
        """
        Основной процесс синхронизации.
        Выполняется в отдельном потоке.
        """
        try:
            self._is_synchronizing = True
            logger.debug("Начало процесса синхронизации...")
            
            # Сканируем файловую систему
            projects_from_fs = self._scan_files_for_projects()
            
            # Получаем проекты из базы данных
            projects_from_db = self._get_projects_from_database()
            
            # Выполняем синхронизацию
            self._sync_projects(projects_from_db, projects_from_fs)
            
            logger.debug("Синхронизация успешно завершена")
            
        except Exception as e:
            logger.error(f"Ошибка в процессе синхронизации: {e}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
        finally:
            self._is_synchronizing = False

    @log_exception
    def _scan_files_for_projects(self) -> Dict[str, str]:
        """
        Сканирует файловую систему для поиска проектов.
        
        Returns:
            Dict[str, str]: Словарь {относительный_путь: uid_из_файла}
        """
        logger.debug(f"Чтение проектов из файловой системе")
        result = {}

        try:
            # Ищем все файлы .geo_office_project рекурсивно
            for project_file in self.projects_root_path.rglob(PROJECT_FILE_NAME):
                # Пропускаем файлы из папки шаблона
                if FileUtils.get_relative_path(self.template_exc_path, project_file):
                    continue
                    
                # Читаем содержимое файла
                uid_content = ProjectFileUtils.read_project_file(project_file)
                if uid_content is None:
                    continue
                    
                # Вычисляем относительный путь к папке проекта
                project_dir_path = project_file.parent
                rel_path = FileUtils.get_relative_path(self.projects_root_path, project_dir_path)
                
                if rel_path is not None:
                    result[str(rel_path)] = uid_content
                    logger.debug(f"\tПроект: path=`{rel_path}` UID=`{uid_content}`")
                    
            logger.debug(f"Чтение проектов завершен. Найдено проектов: {len(result)}")
            return result
            
        except Exception:
            logger.error(f"Ошибка при чтении проектов из файловой системы: {traceback.format_exc()}")
            return {}

    @log_exception
    def _get_projects_from_database(self) -> Dict[str, str]:
        """
        Получает все проекты из базы данных.
        
        Returns:
            Dict[str, str]: Словарь {относительный_путь: uid}
        """
        logger.debug(f"Чтение проектов из БД (кроме проектов со статусом `deleted`)")
        result = {}
        
        try:
            all_projects = self.database_service.get_all_projects()
            
            for project in all_projects:
                if project.status != "deleted":  # Игнорируем удаленные проекты
                    result[project.path] = project.uid
                    logger.debug(f"\tПроект: path=`{project.path}` UID=`{project.uid}`")
                    
            logger.debug(f"Чтение проектов завершен. Найдено проектов: {len(result)}")
            return result
            
        except Exception:
            logger.error(f"Ошибка при чтении проектов из БД: {traceback.format_exc()}")
            return {}

    @log_exception
    def _sync_projects(self, projects_from_db: Dict[str, str], projects_from_fs: Dict[str, str]) -> None:
        """
        Синхронизирует проекты между базой данных и файловой системой.
        
        Args:
            projects_from_db: Проекты из базы данных
            projects_from_fs: Проекты из файловой системы
        """
        logger.debug(f"Синхронизация объектов")
        try:
            # Собираем все UID из БД и файлов
            db_uids = set()
            file_uids = set()
            
            # UID из БД
            for path, uid in projects_from_db.items():
                if ProjectFileUtils.is_uid(uid):
                    db_uids.add(uid)

            # UID из файлов
            for path, uid in projects_from_fs.items():
                if ProjectFileUtils.is_uid(uid):
                    file_uids.add(uid)
            
            # # Обрабатываем UID, которые есть и в БД, и в файлах
            # # FIXME: Проверить и исправить алгоритм обработки
            # common_uids = db_uids & file_uids
            # self._sync_common_uids(common_uids, projects_from_db, projects_from_fs)
            #
            # # Обрабатываем UID, которые есть только в БД
            # # FIXME: Проверить и исправить алгоритм обработки
            # db_only_uids = db_uids - file_uids
            # self._sync_db_only_uids(db_only_uids)
            #
            # # Обрабатываем UID, которые есть только в файлах
            # # FIXME: Проверить и исправить алгоритм обработки
            # file_only_uids = file_uids - db_uids
            # self._sync_file_only_uids(file_only_uids, projects_from_fs)

            # Обрабатываем файлы без UID
            # FIXME: Проверить и исправить алгоритм обработки
            self._sync_files_without_uid(projects_from_fs)
            
        except Exception:
            logger.error(f"Ошибка при синхронизации проектов: {traceback.format_exc()}")

    @log_exception
    def _sync_common_uids(self, common_uids: set, projects_from_db: Dict[str, str], 
                         projects_from_fs: Dict[str, str]) -> None:
        """
        Синхронизирует UID, которые присутствуют и в БД, и в файлах.
        
        Args:
            common_uids: Набор общих UID
            projects_from_db: Проекты из базы данных
            projects_from_fs: Проекты из файловой системы
        """
        for uid in common_uids:
            try:
                # Находим путь в БД и в файлах для этого UID
                db_path = None
                file_path = None
                
                for path, path_uid in projects_from_db.items():
                    if path_uid == uid:
                        db_path = path
                        break
                
                for path, path_uid in projects_from_fs.items():
                    if path_uid == uid:
                        file_path = path
                        break
                
                if db_path and file_path:
                    if db_path != file_path:
                        # Пути не совпадают - обновляем путь в БД
                        project = self.database_service.get_project_from_uid(uid)
                        if project:
                            self.database_service.update_project_path(project.id, file_path)
                            logger.info(f"Обновлен путь проекта {project.number} {project.name}: {db_path} -> {file_path}")
                    # else:
                    #     # Всё синхронизировано
                    #     logger.debug(f"Проект {uid} уже синхронизирован")
                        
            except Exception as e:
                logger.error(f"Ошибка при синхронизации UID {uid}: {e}")
                continue

    @log_exception
    def _sync_db_only_uids(self, db_only_uids: set) -> None:
        """
        Обрабатывает UID, которые есть только в базе данных.
        
        Args:
            db_only_uids: UID, присутствующие только в БД
        """
        for uid in db_only_uids:
            try:
                project = self.database_service.get_project_from_uid(uid)
                if project:
                    self.database_service.mark_deleted_project(project.id)
                    logger.info(f"Проект помечен как удаленный (файл не найден): {uid}")
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке UID только в БД {uid}: {e}")
                continue

    @log_exception
    def _sync_file_only_uids(self, file_only_uids: set, projects_from_fs: Dict[str, str]) -> None:
        """
        Обрабатывает UID, которые есть только в файлах.
        
        Args:
            file_only_uids: UID, присутствующие только в файлах
            projects_from_fs: Проекты из файловой системы
        """
        for uid in file_only_uids:
            try:
                # Находим путь к файлу
                file_path = None
                for path, path_uid in projects_from_fs.items():
                    if path_uid == uid:
                        file_path = path
                        break

                if file_path:
                    # Создаем новый проект
                    project_name = Path(file_path).name
                    self.database_service.create_project(
                        name=project_name,
                        path=file_path,
                        uid=uid
                    )
                    logger.info(f"Добавлен новый проект в БД: {file_path} (UID: {uid})")
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке UID только в файлах {uid}: {e}")
                continue

    @log_exception
    def _sync_files_without_uid(self, projects_from_fs: Dict[str, str]) -> None:
        """
        Обрабатывает файлы проектов без UID.
        
        Args:
            projects_from_fs: Проекты из файловой системы
        """
        logger.debug(f"Синхронизация проектов без UID (добавление в БД)")
        for rel_path, uid in projects_from_fs.items():
            if not ProjectFileUtils.is_uid(uid):
                try:
                    absolute_path = self.projects_root_path / rel_path / PROJECT_FILE_NAME
                    # Создаем новый UID и добавляем в файл и БД
                    uid = ProjectFileUtils.set_uid(absolute_path)
                    
                    project_name = absolute_path.parent.name
                    self.database_service.create_project(
                        name=project_name,
                        path=rel_path,
                        uid=uid
                    )
                    logger.debug(f"Добавлен в БД проект: path=`{rel_path}` name=`{project_name}` UID=`{uid}`")
                    
                except Exception:
                    logger.error(f"Ошибка при добавлении проекта в БД (path=`{rel_path}`): {traceback.format_exc()}")
                    continue

    def is_synchronizing(self) -> bool:
        """
        Проверяет, выполняется ли в данный момент синхронизация.
        
        Returns:
            bool: True если синхронизация выполняется, False иначе
        """
        return self._is_synchronizing
