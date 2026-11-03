import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image, ImageDraw
from cleanplate.engine import Settings
from cleanplate.media import run, executable


def main():
    folder = Path(__file__).resolve().parents[1] / 'demo'
    folder.mkdir(exist_ok=True)
    yy, xx = np.indices((360, 640))
    plate = np.stack((35 + xx // 8, 65 + yy // 5, 100 + xx // 12), axis=2).astype(np.uint8)
    Image.fromarray(plate).save(folder / 'cenario.png')
    image = Image.fromarray(plate)
    draw = ImageDraw.Draw(image)
    draw.ellipse((265, 65, 365, 165), fill=(220, 160, 115))
    draw.rounded_rectangle((235, 160, 395, 340), radius=38, fill=(165, 45, 40))
    draw.rounded_rectangle((200, 175, 245, 310), radius=20, fill=(220, 160, 115))
    draw.rounded_rectangle((385, 175, 430, 310), radius=20, fill=(220, 160, 115))
    image.save(folder / 'objeto.png')
    run([executable('ffmpeg'), '-v', 'error', '-y', '-loop', '1', '-i', str(folder / 'objeto.png'),
         '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-t', '2', '-r', '24',
         '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(folder / 'video.mp4')])
    settings = Settings(outline_enabled=False, shadow_enabled=False, glow_enabled=False)
    project = {'version': 3, 'source': 'video.mp4', 'reference': 'cenario.png',
               'settings': settings.to_dict(), 'reference_start': 0, 'reference_duration': 3}
    (folder / 'projeto.json').write_text(json.dumps(project, indent=2), encoding='utf-8')
    print(folder)


if __name__ == '__main__':
    main()
