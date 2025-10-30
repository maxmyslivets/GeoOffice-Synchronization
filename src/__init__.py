import os
from pathlib import Path

APP_NAME = "GeoOffice-Synchronization"

APP_DIR = Path(os.path.expanduser("~/Documents")) / APP_NAME
APP_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH = APP_DIR / "settings.json"

PROJECT_FILE_NAME = ".geo_office_project"
