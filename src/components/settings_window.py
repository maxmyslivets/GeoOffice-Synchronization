import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from typing import Callable

from src.utils.logger_config import get_logger

logger = get_logger("components.settings_window")


class SettingsWindow:
    """Окно настроек приложения."""
    
    def __init__(self, server_path: str, database_path: str, on_save: Callable[[str, str], None]):
        """
        Инициализация окна настроек.
        
        Args:
            server_path: Текущий путь к файловому серверу
            database_path: Текущий путь к базе данных
            on_save: Callback-функция для сохранения настроек (принимает server_path и database_path)
        """
        self.server_path = server_path
        self.database_path = database_path
        self.on_save = on_save
        
        self._create_window()
    
    def _create_window(self):
        """Создает и показывает окно настроек."""
        self.window = tk.Tk()
        self.window.title("Настройки синхронизации")
        self.window.geometry("400x180")
        self.window.resizable(False, False)
        
        # Путь к файловому серверу
        tk.Label(self.window, text="Путь к файловому серверу:").pack(anchor='w', padx=10, pady=(10, 0))
        self.server_var = tk.StringVar(value=self.server_path)
        path_frame = tk.Frame(self.window)
        path_frame.pack(fill='x', padx=10)
        tk.Entry(path_frame, textvariable=self.server_var).pack(side='left', fill='x', expand=True)
        ttk.Button(path_frame, text="Обзор...", command=self._browse_folder).pack(side='right', padx=5)
        
        # Имя базы данных
        tk.Label(self.window, text="Имя базы данных:").pack(anchor='w', padx=10, pady=(10, 0))
        self.database_var = tk.StringVar(value=str(self.database_path))
        ttk.Entry(self.window, textvariable=self.database_var, width=30).pack(padx=10, anchor='w')
        
        # Кнопка сохранения
        ttk.Button(self.window, text="Сохранить", command=self._save_settings).pack(pady=20)
        
        self.window.mainloop()
    
    def _browse_folder(self):
        """Открывает диалог выбора папки."""
        path = filedialog.askdirectory(title="Выберите папку с проектами")
        if path:
            self.server_var.set(path)
    
    def _save_settings(self):
        """Сохраняет настройки и закрывает окно."""
        try:
            server_path = self.server_var.get().strip()
            database_path = self.database_var.get().strip()
            
            # Вызываем callback для сохранения
            self.on_save(server_path, database_path)
            
            # Закрываем окно
            self.window.destroy()
            logger.info("Настройки сохранены через окно настроек")
        except Exception as e:
            logger.exception("Ошибка при сохранении настроек из окна")
            # Можно добавить показ ошибки пользователю
            from src.utils.error_window import show_error
            show_error(f"Ошибка при сохранении настроек:\n{str(e)}")


def open_settings_window(server_path: str, database_path: str, on_save: Callable[[str, str], None]):
    """
    Открывает окно настроек.
    
    Args:
        server_path: Текущий путь к файловому серверу
        database_path: Текущий путь к базе данных
        on_save: Callback-функция для сохранения настроек
    """
    SettingsWindow(server_path, database_path, on_save)
