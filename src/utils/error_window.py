import tkinter as tk
from tkinter import messagebox

from src import APP_NAME

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
