import traceback
import uuid
from datetime import datetime
from typing import Any

import pystray
from pony.orm import Database as PonyDatabase
from pony.orm import PrimaryKey, Optional, Required, db_session
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter import messagebox
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import threading
import json

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from src import APP_NAME, PROJECT_FILE_NAME


def show_error(message: str, title: str = APP_NAME):
    """Показывает окно ошибки через Tkinter (работает из любого потока)."""
    try:
        root = tk.Tk()
        root.withdraw()  # скрываем главное окно
        messagebox.showerror(title, message)
        root.destroy()
    except Exception as e:
        # fallback, если GUI недоступен (например, на сервере без дисплея)
        print(f"[{title}] {message}\n(Не удалось показать окно: {e})")


class GeoOfficeProjectHandler(FileSystemEventHandler):
    def __init__(self, func_created, func_moved, func_deleted):
        super().__init__()
        self.func_created = func_created
        self.func_moved = func_moved
        self.func_deleted = func_deleted

    def on_created(self, event):
        if not event.is_directory and Path(event.src_path).name == PROJECT_FILE_NAME:
            self.func_created(event.src_path)

    def on_moved(self, event):
        if not event.is_directory and Path(event.src_path).name == PROJECT_FILE_NAME:
            self.func_moved(event.src_path)

    def on_deleted(self, event):
        self.func_deleted(event.src_path)


def is_network_path(path: str | Path) -> bool:
    """
    Определяет, является ли путь сетевым.
    Работает для Windows-путей вида \\SERVER\Share или дисков, смонтированных из сети.
    """
    path = str(path)
    # Проверяем UNC-путь (начинается с двойного слеша)
    if path.startswith(r"\\"):
        return True
    # Проверяем, не смонтирован ли диск из сети
    drive = os.path.splitdrive(path)[0]
    if drive:
        try:
            import ctypes
            DRIVE_REMOTE = 4
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\")
            return drive_type == DRIVE_REMOTE
        except Exception:
            pass
    return False


class GeoOfficeProjectSyncTrayApp:
    """Класс приложения для трея GeoOffice_ProjectSync с логированием, ротацией и периодической синхронизацией."""

    def __init__(self):
        self.is_running = False
        self.server_path = ""
        self.database_path = ""
        self._sync_thread = None
        self._stop_event = threading.Event()

        # Настройка путей
        self.documents_path = Path(os.path.expanduser("~/Documents"))
        self.geooffice_dir = self.documents_path / "GeoOffice"
        self.geooffice_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.geooffice_dir / "settings.json"


        # Загружаем сохранённые настройки (если есть)
        self._load_settings()

        self._init_database()

        self._init_observer()

        # Создаем иконку
        self.icon = pystray.Icon(
            name='GeoOffice_ProjectSync',
            title='GeoOffice Мониторинг остановлен',
            icon=self._draw_icon(),
            menu=self._create_menu()
        )

    # --- Методы работы с настройками ---------------------------------------

    def _save_settings(self):
        """Сохраняет настройки в JSON файл."""
        try:
            data = {"server_path": self.server_path, "database_path": self.database_path}
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logging.info(f"Настройки сохранены в {self.settings_file}")
        except Exception as e:
            logging.exception("Ошибка при сохранении настроек")
            show_error("Ошибка при сохранении настроек")

    def _load_settings(self):
        """Загружает настройки (если файл существует)."""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.server_path = data.get("server_path", "")
                self.database_path = data.get("database_path", "")
                logging.info(f"Настройки загружены: сервер = {self.server_path or 'не задан'}")
            else:
                logging.info("Файл настроек не найден, используется конфигурация по умолчанию.")
        except Exception as e:
            logging.exception("Ошибка при загрузке настроек")
            show_error("Ошибка при загрузке настроек")

    def _init_database(self):
        self.db = Database(Path(self.server_path) / self.database_path)

    def _init_observer(self):
        """Инициализация наблюдателя (создаётся заново при каждом запуске)."""
        try:
            path = Path(self.server_path) / self.db.get_project_dir()
            if not path.exists():
                logging.warning(f"Папка для наблюдения не найдена: {path}")
                return

            network = is_network_path(path)
            observer_class = PollingObserver if network else Observer
            event_handler = GeoOfficeProjectHandler(self.watch_func_created, self.watch_func_moved,
                                                    self.watch_func_deleted)

            # Если старый наблюдатель существует — корректно завершаем
            if hasattr(self, "observer") and self.observer is not None:
                try:
                    self.observer.stop()
                    self.observer.join(timeout=2)
                except Exception:
                    pass

            # Создаём новый наблюдатель
            self.observer = observer_class()
            self.observer.schedule(event_handler, str(path), recursive=True)
            logging.info(f"Создан наблюдатель ({'сетевой' if network else 'локальный'}) для пути: {path}")

        except Exception:
            logging.exception("Ошибка при инициализации наблюдателя")
            show_error(f"Ошибка при инициализации наблюдателя:\n{traceback.format_exc()}")

    def watch_func_created(self, filepath):
        """Обработка создания нового файла .geo_office_project"""
        try:
            logging.info(f"Обнаружен новый файл проекта: {filepath}")
            
            # Проверяем, что файл существует (могут быть race conditions)
            project_file = Path(filepath)
            if not project_file.exists():
                logging.warning(f"Файл не найден после создания: {filepath}")
                return
            
            # Вычисляем относительный путь от server_path + project_dir
            rel_path = self._get_relative_project_path(filepath)
            if rel_path is None:
                logging.warning(f"Не удалось определить относительный путь для {filepath}")
                return
            
            # Читаем UID из файла
            try:
                with project_file.open("r", encoding="utf-8") as f:
                    uid_content = f.read().strip()
            except Exception as e:
                logging.exception(f"Ошибка при чтении файла {filepath}: {e}")
                uid_content = ""
            
            # Проверяем, валидный ли UID
            if self._is_uid(uid_content):
                uid = uid_content
                logging.info(f"Найден валидный UID в файле: {uid}")
            else:
                # Создаем новый UID и записываем в файл
                uid = str(uuid.uuid4())
                try:
                    with project_file.open("w", encoding="utf-8") as f:
                        f.write(uid)
                    logging.info(f"Создан новый UID для проекта: {uid}")
                except Exception as e:
                    logging.exception(f"Ошибка при записи UID в файл {filepath}: {e}")
                    return
            
            # Создаем проект в БД
            try:
                self.db.create_project(rel_path, uid)
                logging.info(f"Проект добавлен в БД: {rel_path} (UID: {uid})")
            except Exception as e:
                logging.exception(f"Ошибка при создании проекта в БД: {e}")
                
        except Exception as e:
            logging.exception(f"Ошибка при обработке создания файла {filepath}: {e}")

    def watch_func_moved(self, filepath):
        """Обработка перемещения файла .geo_office_project"""
        try:
            logging.info(f"Обнаружено перемещение файла проекта: {filepath}")
            
            # Проверяем, что файл существует
            project_file = Path(filepath)
            if not project_file.exists():
                logging.warning(f"Файл не найден после перемещения: {filepath}")
                return
            
            # Вычисляем относительный путь
            rel_path = self._get_relative_project_path(filepath)
            if rel_path is None:
                logging.warning(f"Не удалось определить относительный путь для {filepath}")
                return
            
            # Читаем UID из файла
            try:
                with project_file.open("r", encoding="utf-8") as f:
                    uid = f.read().strip()
            except Exception as e:
                logging.exception(f"Ошибка при чтении файла {filepath}: {e}")
                return
            
            # Проверяем, валидный ли UID
            if not self._is_uid(uid):
                logging.warning(f"UID в файле невалидный: {uid}")
                return
            
            # Обновляем путь в БД
            try:
                self.db.update_project_path(uid, rel_path)
                logging.info(f"Путь проекта обновлен в БД: {rel_path} (UID: {uid})")
            except Exception as e:
                logging.exception(f"Ошибка при обновлении пути проекта в БД: {e}")
                
        except Exception as e:
            logging.exception(f"Ошибка при обработке перемещения файла {filepath}: {e}")

    def watch_func_deleted(self, filepath):
        """Обработка удаления файла или папки"""
        try:
            file_path = Path(filepath)
            
            # Если удален файл .geo_office_project
            if file_path.name == PROJECT_FILE_NAME:
                logging.info(f"Обнаружено удаление файла проекта: {filepath}")
                
                # Вычисляем относительный путь
                rel_path = self._get_relative_project_path(filepath)
                if rel_path is None:
                    logging.warning(f"Не удалось определить относительный путь для {filepath}")
                    return
                
                # Помечаем проект как удаленный по относительному пути
                try:
                    # Получаем UID из БД по пути
                    all_projects = self.db.get_all_projects()
                    for path, uid in all_projects.items():
                        if path == rel_path:
                            self.db.mark_project_as_deleted(uid)
                            logging.info(f"Проект помечен как удаленный: {rel_path} (UID: {uid})")
                            return
                    
                    logging.warning(f"Проект с путем {rel_path} не найден в БД")
                except Exception as e:
                    logging.exception(f"Ошибка при пометке проекта как удаленного: {e}")
            
            # Если удалена папка - проверяем, не является ли она проектом
            elif not file_path.suffix:  # вероятно, это папка
                logging.info(f"Обнаружено удаление папки: {filepath}")
                
                # Вычисляем относительный путь
                rel_path = self._get_relative_project_path(filepath)
                if rel_path is None:
                    logging.warning(f"Не удалось определить относительный путь для {filepath}")
                    return
                
                # Проверяем, есть ли в этой папке или в подпапках проекты
                try:
                    all_projects = self.db.get_all_projects()
                    for path, uid in all_projects.items():
                        # Проверяем, является ли удаленная папка частью пути проекта
                        if path.startswith(rel_path):
                            self.db.mark_project_as_deleted(uid)
                            logging.info(f"Проект помечен как удаленный (папка удалена): {path} (UID: {uid})")
                except Exception as e:
                    logging.exception(f"Ошибка при пометке проектов как удаленных: {e}")
                    
        except Exception as e:
            logging.exception(f"Ошибка при обработке удаления {filepath}: {e}")

    def _get_relative_project_path(self, filepath: str | Path) -> str | None:
        """
        Вычисляет относительный путь проекта от server_path + project_dir.
        Возвращает None, если путь не соответствует ожидаемой структуре.
        """
        try:
            file_path = Path(filepath)
            
            # Если это файл .geo_office_project, получаем путь к папке проекта
            if file_path.name == PROJECT_FILE_NAME:
                project_dir_path = file_path.parent
            else:
                project_dir_path = file_path
            
            # Получаем полный путь к директории проектов
            projects_root = Path(self.server_path) / self.db.get_project_dir()
            
            # Вычисляем относительный путь
            try:
                rel_path = project_dir_path.relative_to(projects_root)
                return str(rel_path)
            except ValueError:
                # Путь не находится внутри projects_root
                logging.warning(f"Путь {project_dir_path} не находится внутри {projects_root}")
                return None
                
        except Exception as e:
            logging.exception(f"Ошибка при вычислении относительного пути для {filepath}: {e}")
            return None

    # --- Методы действий ----------------------------------------------------

    def start_action(self, icon=None, menu_item=None):
        """Запускает мониторинг файловой системы в отдельном потоке."""
        try:
            if self.is_running:
                logging.info("Мониторинг уже запущен.")
                return

            if not self.server_path:
                show_error("Не указан путь к серверу. Откройте настройки и задайте путь.")
                return

            # Каждый запуск создаёт новый observer
            self._init_observer()

            def _start_observer():
                try:
                    if not self.observer:
                        logging.error("Не удалось создать наблюдатель — запуск отменён.")
                        return
                    logging.info(f"Запуск наблюдателя за {self.server_path}")
                    self.observer.start()
                    self.is_running = True
                    self.icon.title = 'GeoOffice Мониторинг запущен'
                    self._update_menu()
                except RuntimeError as re:
                    # Этот случай как раз при попытке повторного запуска потока
                    logging.warning(f"Попытка повторного запуска observer: {re}")
                    self._init_observer()
                    self.observer.start()
                except Exception:
                    logging.exception("Ошибка при запуске наблюдателя")
                    show_error(f"Ошибка при запуске наблюдателя:\n{traceback.format_exc()}")

            threading.Thread(target=_start_observer, daemon=True).start()

        except Exception:
            logging.exception("Ошибка при запуске мониторинга")
            show_error(f"Ошибка при запуске мониторинга:\n{traceback.format_exc()}")

    def stop_action(self, icon=None, menu_item=None):
        """Останавливает мониторинг безопасно (без зависаний потоков)."""
        try:
            if not self.is_running:
                logging.info("Мониторинг уже остановлен.")
                return

            def _stop_observer():
                try:
                    logging.info("Остановка наблюдателя...")
                    if self.observer:
                        self.observer.stop()
                        self.observer.join(timeout=3)
                    self.is_running = False
                    self.icon.title = 'GeoOffice Мониторинг остановлен'
                    self._update_menu()
                    logging.info("Мониторинг успешно остановлен.")
                except Exception:
                    logging.exception("Ошибка при остановке наблюдателя")
                    show_error(f"Ошибка при остановке наблюдателя:\n{traceback.format_exc()}")
                finally:
                    # После остановки обнуляем observer — чтобы можно было безопасно пересоздать
                    self.observer = None

            threading.Thread(target=_stop_observer, daemon=True).start()

        except Exception:
            logging.exception("Ошибка при остановке мониторинга")
            show_error(f"Ошибка при остановке мониторинга:\n{traceback.format_exc()}")

    def settings_action(self, icon, menu_item):
        """Открывает окно настроек."""
        try:
            self._open_settings_window()
        except Exception as e:
            logging.exception(f"Ошибка при открытии окна настроек:\n{traceback.format_exc()}")
            show_error(f"Ошибка при открытии окна настроек:\n{traceback.format_exc()}")

    def exit_action(self, icon, menu_item):
        try:
            logging.info("Выход из приложения...")
            self._stop_event.set()
            self.icon.stop()
        except Exception as e:
            logging.exception(f"Ошибка при выходе из приложения:\n{traceback.format_exc()}")
            show_error(f"Ошибка при выходе из приложения:\n{traceback.format_exc()}")

    def synchronization(self):
        """Запускает синхронизацию в фоновом потоке"""

        def _synchronization():
            """Процесс синхронизации."""
            self.stop_action()

            if (not self.server_path) or (not self.database_path):
                logging.warning("Сервер или база данных не заданы. Синхронизация не выполнена.")
                show_error("Сервер или база данных не заданы. Синхронизация не выполнена.")
                return

            old_title = self.icon.title
            self.icon.title = 'GeoOffice Синхронизация...'

            logging.info(f"Выполняется синхронизация с сервером: {self.server_path}")
            projects_from_db = self.db.get_all_projects()
            projects_from_fs = self._scan_files(path=Path(self.server_path) / self.db.get_project_dir(),
                                                template_exc_path=self.db.get_template_dir())
            self._sync_projects(projects_from_db, projects_from_fs)

            self.icon.title = old_title
            logging.info("Синхронизация завершена успешно.")

            self.start_action()

        self._sync_thread = threading.Thread(target=_synchronization, name="GeoOffice synchronization", daemon=True)
        self._sync_thread.start()

    def _scan_files(self, path: Path | str, template_exc_path: Path | str) -> dict[str, str]:
        result = {}
        for file in path.rglob(PROJECT_FILE_NAME):
            if file.parent == path / template_exc_path:
                continue
            with file.open("r", encoding="utf-8") as f:
                data = f.read()
            result[str(file.parent.relative_to(path))] = data
        return result

    def _is_uid(self, uid: str) -> bool:
        try:
            uuid.UUID("{" + f"{uid}" + "}")
            return True
        except ValueError:
            return False

    def _add_uid_to_file(self, path: str, uid: str) -> None:
        """Добавляет UID в файл .geo_office_project."""
        try:
            # Получаем путь к папке проектов из настроек БД
            db = Database(Path(self.server_path) / self.database_path)
            project_dir = db.get_project_dir()
            project_path = Path(self.server_path) / project_dir / path / PROJECT_FILE_NAME

            with project_path.open("w", encoding="utf-8") as f:
                f.write(uid)
            logging.debug(f"UID {uid} записан в файл {project_path}")
        except Exception as e:
            logging.exception(f"Ошибка при записи UID в файл {path}: {e}")
            raise

    def _sync_projects(self, in_database: dict[str: str], in_files: dict[str: str]) -> None:
        """
        Синхронизирует проекты между базой данных и файловой системой на основе UID.
        
        Новая логика синхронизации:
        1. Собираем все UID из БД и файлов
        2. Для каждого UID проверяем:
           - Если UID есть в БД и в файлах - проверяем соответствие путей
           - Если UID есть только в БД - ищем файл по UID, если не найден - удаляем из БД
           - Если UID есть только в файлах - добавляем в БД
        3. Для файлов без UID - создаем новый проект с новым UID
        """
        db = Database(Path(self.server_path) / self.database_path)

        # Собираем все UID из БД и файлов
        db_uids = set()
        file_uids = set()

        # UID из БД
        for path, uid in in_database.items():
            if self._is_uid(uid):
                db_uids.add(uid)

        # UID из файлов
        for path, uid in in_files.items():
            if self._is_uid(uid):
                file_uids.add(uid)

        # Обрабатываем UID, которые есть и в БД, и в файлах
        common_uids = db_uids & file_uids
        for uid in common_uids:
            try:
                # Находим путь в БД и в файлах для этого UID
                db_path = None
                file_path = None

                for path, path_uid in in_database.items():
                    if path_uid == uid:
                        db_path = path
                        break

                for path, path_uid in in_files.items():
                    if path_uid == uid:
                        file_path = path
                        break

                if db_path and file_path:
                    if db_path != file_path:
                        # Пути не совпадают - обновляем путь в БД
                        db.update_project_path(uid, file_path)
                        logging.info(f"Обновлен путь проекта {uid}: {db_path} -> {file_path}")
                    else:
                        # Всё синхронизировано
                        logging.debug(f"Проект {uid} уже синхронизирован")

            except Exception as e:
                logging.exception(f"Ошибка при синхронизации UID {uid}: {e}")
                continue

        # Обрабатываем UID, которые есть только в БД
        db_only_uids = db_uids - file_uids
        for uid in db_only_uids:
            try:
                # UID есть только в БД - помечаем как удаленный (файла нет в доступных)
                db.mark_project_as_deleted(uid)
                logging.info(f"Проект помечен как удаленный (файл не найден): {uid}")

            except Exception as e:
                logging.exception(f"Ошибка при обработке UID только в БД {uid}: {e}")
                continue

        # Обрабатываем UID, которые есть только в файлах
        file_only_uids = file_uids - db_uids
        for uid in file_only_uids:
            try:
                # Находим путь к файлу
                file_path = None
                for path, path_uid in in_files.items():
                    if path_uid == uid:
                        file_path = path
                        break

                if file_path:
                    # Создаем новый проект
                    db.create_project(file_path, uid)
                    logging.info(f"Добавлен новый проект в БД: {file_path} (UID: {uid})")

            except Exception as e:
                logging.exception(f"Ошибка при обработке UID только в файлах {uid}: {e}")
                continue

        # Обрабатываем файлы без UID
        for path, uid in in_files.items():
            if not self._is_uid(uid):
                try:
                    # Создаем новый UID и добавляем в файл и БД
                    new_uid = str(uuid.uuid4())
                    self._add_uid_to_file(path, new_uid)
                    db.create_project(path, new_uid)
                    logging.info(f"Создан новый проект: {path} (UID: {new_uid})")

                except Exception as e:
                    logging.exception(f"Ошибка при создании нового проекта {path}: {e}")
                    continue

    # --- Интерфейс ----------------------------------------------------------

    def _create_menu(self):
        return (
            item('Запустить мониторинг', self.start_action, enabled=not self.is_running),
            item('Остановить мониторинг', self.stop_action, enabled=self.is_running),
            item('Синхронизировать', self.synchronization),
            item('Настройки', self.settings_action),
            item('Выход', self.exit_action)
        )

    def _update_menu(self):
        self.icon.menu = pystray.Menu(*self._create_menu())
        self.icon.update_menu()

    # --- Окно настроек ------------------------------------------------------

    def _open_settings_window(self):
        """Создает и показывает окно настроек."""

        def browse_folder():
            path = filedialog.askdirectory(title="Выберите папку с проектами")
            if path:
                server_var.set(path)

        def save_settings():
            try:
                self.server_path = server_var.get().strip()
                self.database_path = database_var.get().strip()
                self._save_settings()
                settings_win.destroy()
            except Exception as e:
                logging.exception("Ошибка при сохранении настроек")

        settings_win = tk.Tk()
        settings_win.title("Настройки синхронизации")
        settings_win.geometry("400x180")
        settings_win.resizable(False, False)

        tk.Label(settings_win, text="Путь к файловому серверу:").pack(anchor='w', padx=10, pady=(10, 0))
        server_var = tk.StringVar(value=self.server_path)
        path_frame = tk.Frame(settings_win)
        path_frame.pack(fill='x', padx=10)
        tk.Entry(path_frame, textvariable=server_var).pack(side='left', fill='x', expand=True)
        ttk.Button(path_frame, text="Обзор...", command=browse_folder).pack(side='right', padx=5)

        # Период синхронизации
        tk.Label(settings_win, text="Имя базы данных:").pack(anchor='w', padx=10, pady=(10, 0))
        database_var = tk.StringVar(value=str(self.database_path))
        ttk.Entry(settings_win, textvariable=database_var, width=30).pack(padx=10, anchor='w')

        ttk.Button(settings_win, text="Сохранить", command=save_settings).pack(pady=20)
        settings_win.mainloop()

    # --- Отрисовка иконки --------------------------------------------------

    def _draw_icon(self) -> Image:
        img = Image.new('RGB', (64, 64), '#ffffff')
        draw = ImageDraw.Draw(img)

        for y in range(64):
            r = int(0x42 + (0x7e - 0x42) * y / 64)
            g = int(0xa5 + (0x57 - 0xa5) * y / 64)
            b = int(0xf5 + (0xc2 - 0xf5) * y / 64)
            draw.line([(0, y), (64, y)], fill=(r, g, b))

        draw.rounded_rectangle([2, 2, 62, 62], radius=6, outline="#00796b", width=1)
        draw.line([(12, 32), (52, 32)], fill="#004d40", width=1)
        draw.line([(32, 12), (32, 52)], fill="#004d40", width=1)
        draw.ellipse([22, 22, 42, 42], outline="#004d40", width=1)
        draw.line([(26, 15), (32, 5), (38, 15)], fill="#ff7043", width=1)
        draw.line([(28, 10), (36, 10)], fill="#ff7043", width=1)
        draw.arc([24, 24, 40, 40], start=200, end=340, fill="#ff7043", width=1)
        draw.arc([16, 16, 48, 48], start=160, end=300, fill="#ff7043", width=2)
        draw.polygon([(16, 28), (20, 24), (20, 30)], fill="#ff7043")
        draw.arc([16, 16, 48, 48], start=-20, end=120, fill="#ff7043", width=2)
        draw.polygon([(48, 36), (44, 40), (44, 34)], fill="#ff7043")
        return img

    # --- Запуск -------------------------------------------------------------

    def run(self, detached: bool = True):
        try:
            if detached:
                self.icon.run_detached()
            else:
                self.icon.run()
            self.start_action()
            self.synchronization()
        except Exception as e:
            logging.exception("Ошибка при запуске приложения")


class Database:
    def __init__(self, path: Path | str):
        """
        Инициализация моделей базы данных.
        :param db: Экземпляр базы данных Pony ORM
        """
        self.db = PonyDatabase()
        self.db.bind(provider='sqlite', filename=str(path))
        self.models = self._define_models()
        self.db.generate_mapping(check_tables=True, create_tables=True)

    def _define_models(self) -> Any:
        """Определение моделей таблиц базы данных"""

        class ProjectTable(self.db.Entity):
            """
            Модель таблицы проектов.
            Основная таблица для хранения информации о проектах.
            """
            _table_ = "Объекты"
            id = PrimaryKey(int, auto=True)
            name = Required(str)  # Название проекта
            path = Required(str)  # Путь к папке проекта
            uid = Required(str)  # Уникальный идентификатор
            status = Required(str, default="active")  # Статус проекта: active, deleted
            created_date = Required(datetime, default=datetime.now)
            modified_date = Required(datetime, default=datetime.now)

        class SettingsTable(self.db.Entity):
            """
            Модель таблицы настроек.
            """
            _table_ = "Настройки"
            id = PrimaryKey(int, auto=True)
            project_dir = Optional(str, nullable=False)     # путь к папке объектов относительно файлового сервера
            template_project_dir = Optional(str, nullable=False)    # путь к папке шаблона объектов относительно
                                                                    # файлового сервера

        class Models:
            Project = ProjectTable
            Settings = SettingsTable

        return Models

    @db_session
    def get_project_dir(self) -> str:
        return self.models.Settings[1].project_dir

    @db_session
    def get_template_dir(self) -> str:
        return self.models.Settings[1].template_project_dir

    @db_session
    def get_all_projects(self) -> dict[str: str]:
        """Возвращает проекты."""
        projects = self.models.Project.select()[:]
        result = {}
        for project in projects:
            result[project.path] = project.uid
        return result

    @db_session
    def create_project(self, path: Path | str, uid: str) -> Any:
        path = Path(path)
        project = self.models.Project(name=path.name, path=str(path), uid=uid)
        return project

    @db_session
    def get_project_by_uid(self, uid: str) -> Any:
        """Находит проект в БД по UID."""
        return self.models.Project.get(uid=uid)

    @db_session
    def update_project_path(self, uid: str, new_path: str) -> None:
        """Обновляет путь проекта в базе данных по UID."""
        project = self.models.Project.get(uid=uid)
        if project:
            project.path = new_path
            project.modified_date = datetime.now()
            logging.debug(f"Обновлен путь проекта {uid}: {new_path}")
        else:
            logging.warning(f"Проект с UID {uid} не найден в БД для обновления пути")

    @db_session
    def mark_project_as_deleted(self, uid: str) -> None:
        """Помечает проект как удаленный (устанавливает статус 'deleted')."""
        project = self.models.Project.get(uid=uid)
        if project:
            project.status = "deleted"
            project.modified_date = datetime.now()
            logging.debug(f"Проект с UID {uid} помечен как удаленный")
        else:
            logging.warning(f"Проект с UID {uid} не найден в БД для пометки как удаленный")


# --- Точка входа -----------------------------------------------------------

if __name__ == '__main__':
    app = GeoOfficeProjectSyncTrayApp()
    app.run()
