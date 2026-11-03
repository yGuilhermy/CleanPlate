import shutil
import subprocess
import sys
from build_support import ROOT, prepare, bundle_runtime, build_failure, check_destination


def main():
    package = ROOT / 'dist/CleanPlateControl'
    check_destination(package, 'CleanPlateControl.exe')
    env, binaries = prepare(['PyInstaller', 'cv2', 'numpy', 'PIL', 'mcp'])
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--console',
        '--name', 'CleanPlateControl', '--paths', str(ROOT / '.deps'), '--paths', str(ROOT),
        '--icon', str(ROOT / 'cleanplate/assets/icon.ico'),
        '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build/control'),
        '--specpath', str(ROOT / 'build'), '--exclude-module', 'PySide6', '--exclude-module', 'tkinter',
        '--exclude-module', 'scipy', '--exclude-module', 'matplotlib', '--exclude-module', 'pandas',
        '--exclude-module', 'IPython', '--exclude-module', 'pytest',
        str(ROOT / 'tools/control_entry.py')], check=True, cwd=ROOT, env=env)
    bundle_runtime(package, binaries, ['numpy', 'Pillow', 'opencv-python-headless', 'mcp'])
    shutil.copy2(ROOT / 'AUTOMATION.md', package / 'AUTOMATION.md')
    shutil.copytree(ROOT / 'skills/cleanplate-control', package / 'skills/cleanplate-control', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'mcp.example.json', package / 'mcp.example.json')
    print(package / 'CleanPlateControl.exe')


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        build_failure(error)
