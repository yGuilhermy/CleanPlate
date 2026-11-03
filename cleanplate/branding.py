import os
from pathlib import Path

APP_NAME = 'Clean Plate Studio'
RELEASE_STAGE = 'Alfa'
APP_ID = 'CleanPlate.Studio'
ASSETS = Path(__file__).with_name('assets')


def configure_windows_identity():
    if os.name == 'nt':
        import ctypes
        setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        result = setter(APP_ID)
        if result != 0:
            raise OSError('Não foi possível definir a identidade do aplicativo no Windows')


def application_icon():
    from PySide6.QtGui import QIcon
    icon = ASSETS / 'icon.ico'
    return QIcon(str(icon if icon.is_file() else ASSETS / 'icon.svg'))
