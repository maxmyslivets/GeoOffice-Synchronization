import traceback

from src.app import GeoOfficeSyncService
from src.utils.error_window import show_error

if __name__ == '__main__':
    try:
        app = GeoOfficeSyncService()
        app.run()
    except Exception:
        show_error(traceback.format_exc())
