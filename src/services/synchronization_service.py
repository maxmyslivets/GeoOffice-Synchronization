"""
Сервис синхронизации данных GeoOffice.

Обеспечивает синхронизацию между базой данных и файловой системой,
отслеживая изменения в проектах и поддерживая консистентность данных.
"""
import itertools
import queue
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
        
        # Очередь задач синхронизации
        self._sync_queue: queue.Queue = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._is_worker_running = False
        self._is_synchronizing = False
        
        # Пути к папкам проектов и шаблонов
        self.projects_root_path = self.server_path / self.database_service.get_settings_project_dir()
        self.template_exc_path = self.projects_root_path / self.database_service.get_settings_template_project_dir()
        
        # Запускаем worker thread для обработки очереди
        self._start_worker()
        
        logger.info(f"Инициализирован сервис синхронизации для пути: `{self.projects_root_path}`")

    def _start_worker(self) -> None:
        """
        Запускает worker thread для обработки очереди задач синхронизации.
        """
        if not self._is_worker_running:
            self._is_worker_running = True
            self._worker_thread = threading.Thread(
                target=self._worker_process,
                name=f"{APP_NAME}_Worker",
                daemon=True
            )
            self._worker_thread.start()
            logger.debug("Запущен worker thread для обработки очереди синхронизации")

    @log_exception
    def synchronize(self) -> bool:
        """
        Добавляет задачу синхронизации в очередь для обработки.
        Returns:
            bool: True если задача успешно добавлена в очередь, False иначе
        """
        try:
            if not self._validate_paths():
                return False
            # Создаем задачу для синхронизации
            task = {
                'id': str(uuid.uuid4()),
                'timestamp': threading.Event()
            }
            # Добавляем задачу в очередь
            self._sync_queue.put(task)
            logger.debug(f"Задача синхронизации добавлена в очередь (ID=`{task['id']}`)")
            return True
        except Exception:
            logger.error(f"Ошибка при добавлении задачи синхронизации в очередь: {traceback.format_exc()}")
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
            return True
        except Exception:
            logger.error(f"Ошибка при валидации путей: {traceback.format_exc()}")
            return False

    @log_exception
    def _worker_process(self) -> None:
        """
        Worker process для обработки задач синхронизации из очереди.
        Выполняется в отдельном потоке и обрабатывает задачи последовательно.
        """
        logger.debug("Worker process запущен")
        
        while self._is_worker_running:
            try:
                # Ожидаем задачу из очереди
                task = self._sync_queue.get(timeout=1.0)
                # Проверяем на sentinel задачу для завершения работы
                if task is None:
                    logger.debug("Получена sentinel задача, завершение worker process")
                    break
                # Обрабатываем задачу
                self._process_sync_task(task)
                # Отмечаем задачу как выполненную
                self._sync_queue.task_done()
            except queue.Empty:
                # Очередь пуста, продолжаем ожидание
                continue
            except Exception:
                logger.error(f"Ошибка в worker process: {traceback.format_exc()}")
                
        logger.debug("Worker process завершен")

    @log_exception
    def _process_sync_task(self, task: Dict[str, Any]) -> None:
        """
        Обрабатывает отдельную задачу синхронизации.
        
        Args:
            task: Словарь с данными задачи {'id': str, 'timestamp': Event}
        """
        task_id = task['id']
        try:
            self._is_synchronizing = True
            logger.debug(f"Начало выполнения задачи синхронизации ID=`{task_id}`")
            
            # Сканируем файловую систему (с фильтрацией по путям если указано)
            projects_from_fs = self._scan_files_for_projects()
            
            # Получаем проекты из базы данных
            projects_from_db = self._get_projects_from_database()
            
            # Выполняем синхронизацию
            self._sync_projects(projects_from_db, projects_from_fs)
            
            logger.debug(f"Задача синхронизации ID=`{task_id}` успешно завершена")
            
        except Exception:
            logger.error(f"Ошибка в задаче синхронизации ID=`{task_id}`: {traceback.format_exc()}")
        finally:
            self._is_synchronizing = False
            # Устанавливаем событие для уведомления о завершении
            if 'timestamp' in task and task['timestamp']:
                task['timestamp'].set()

    @log_exception
    def _scan_files_for_projects(self) -> Dict[str, str]:
        """
        Сканирует файловую систему для поиска проектов.
        
        Returns:
            Dict[str, str]: Словарь {относительный_путь: uid_из_файла}
        """
        logger.debug(f"Чтение проектов из файловой системы")

        try:
            # Ищем все файлы .geo_office_project рекурсивно
            result = {}
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
            logger.debug(f"Чтение проектов ФС завершено. Найдено проектов: {len(result)}")
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
                    if project.path in result:
                        pass    # FIXME: Что делать с проектами с одинаковыми путями в БД ?
                    result[project.path] = project.uid
                    logger.debug(f"\tПроект: path=`{project.path}` UID=`{project.uid}`")
                    
            logger.debug(f"Чтение проектов БД завершено. Найдено проектов: {len(result)}")
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
            
            # Обрабатываем UID, которые есть и в БД, и в файлах
            common_uids = db_uids & file_uids
            self._sync_common_uids(common_uids, projects_from_db, projects_from_fs)

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
            self._sync_files_without_uid(projects_from_fs)
            
        except Exception:
            logger.error(f"Ошибка при синхронизации проектов: {traceback.format_exc()}")

    @log_exception
    def _sync_common_uids(self, common_uids: set, projects_from_db: Dict[str, str],
                         projects_from_fs: Dict[str, str]) -> None:
        """
        Синхронизирует UID, которые присутствуют и в БД, и в файлах.
        
        Args:
            common_uids: Набор общих UID (ФС + БД). Множество {UID}
            projects_from_db: Проекты из базы данных. Словарь {path: UID}
            projects_from_fs: Проекты из файловой системы. Словарь {path: UID}
        """
        logger.debug(f"Синхронизация проектов с UID (обновление в БД)")
        i=0
        for uid in common_uids:
            try:
                db_rel_path = None
                fs_rel_path = None
                for path, path_uid in projects_from_db.items():
                    if path_uid == uid:
                        db_rel_path = path
                        break
                for path, path_uid in projects_from_fs.items():
                    if path_uid == uid:
                        fs_rel_path = path
                        break
                if db_rel_path and fs_rel_path:
                    if db_rel_path != fs_rel_path:
                        project = self.database_service.get_project_from_uid(uid)
                        if project:
                            self.database_service.update_project_path(project.id, fs_rel_path)
                            if project.name.startswith(self.template_exc_path.name):
                                self.database_service.update_project_name(project.id, Path(fs_rel_path).name)
                            i+=1
                            logger.info(f"Обновлен путь проекта в БД: {db_rel_path} -> {fs_rel_path}")
            except Exception:
                logger.error(f"Ошибка при синхронизации проектов с UID (обновление в БД): {traceback.format_exc()}")
                continue
        logger.debug(f"Обновлено в БД проектов: {i}")

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
        i = 0
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
                    i+=1
                    logger.info(f"Добавлен в БД проект: path=`{rel_path}` name=`{project_name}` UID=`{uid}`")
                    
                except Exception:
                    logger.error(f"Ошибка при добавлении проекта в БД (path=`{rel_path}`): {traceback.format_exc()}")
                    continue
        logger.debug(f"Добавлено в БД проектов: {i}")

    def is_synchronizing(self) -> bool:
        """
        Проверяет, выполняется ли в данный момент синхронизация.
        
        Returns:
            bool: True если синхронизация выполняется, False иначе
        """
        return self._is_synchronizing

    def shutdown(self) -> None:
        """
        Корректно завершает работу сервиса синхронизации.
        Останавливает worker thread и очищает очередь.
        """
        logger.debug("Завершение работы сервиса синхронизации...")
        
        # Останавливаем worker thread
        self._is_worker_running = False
        
        # Добавляем sentinel задачу для принудительного завершения очереди
        try:
            self._sync_queue.put_nowait(None)
        except queue.Full:
            pass
            
        # Ожидаем завершения worker thread
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=60.0)
            if self._worker_thread.is_alive():
                logger.warning("Worker thread не завершился в течение 60 секунд")
        
        logger.info("Сервис синхронизации корректно завершен")
