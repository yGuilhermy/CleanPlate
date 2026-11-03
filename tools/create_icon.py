from io import BytesIO
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.deps'))
from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication, QIcon


def main():
    application = QGuiApplication.instance() or QGuiApplication([])
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    icon = QIcon(str(ROOT / 'cleanplate/assets/icon.svg'))
    if not icon.pixmap(256, 256).save(buffer, 'PNG'):
        raise RuntimeError('Não foi possível renderizar o ícone')
    image = Image.open(BytesIO(bytes(buffer.data()))).convert('RGBA')
    image.save(ROOT / 'cleanplate/assets/icon.ico', format='ICO',
               sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])


if __name__ == '__main__':
    main()
