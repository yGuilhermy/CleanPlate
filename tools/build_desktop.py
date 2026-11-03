from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from build_support import ROOT, prepare, bundle_runtime, build_failure, check_destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist-dir', type=Path, default=ROOT / 'dist')
    destination = parser.parse_args().dist_dir.resolve()
    package = destination / 'Clean Plate Studio'
    check_destination(package, 'Clean Plate Studio.exe')
    env, binaries = prepare(['PyInstaller', 'PySide6', 'cv2', 'numpy', 'PIL'])
    from create_icon import main as create_icon
    create_icon()
    icon = ROOT / 'cleanplate/assets/icon.ico'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed',
        '--name', 'Clean Plate Studio', '--paths', str(ROOT / '.deps'), '--paths', str(ROOT),
        '--distpath', str(destination), '--workpath', str(ROOT / 'build/desktop'),
        '--specpath', str(ROOT / 'build'), '--icon', str(icon),
        '--add-data', str(ROOT / 'cleanplate/assets') + ';cleanplate/assets',
        '--exclude-module', 'tkinter', '--exclude-module', 'scipy', '--exclude-module', 'matplotlib',
        '--exclude-module', 'pandas', '--exclude-module', 'PyQt5', '--exclude-module', 'PyQt6',
        '--exclude-module', 'PySide2', '--exclude-module', 'IPython',
        str(ROOT / 'tools/desktop_entry.py')], check=True, cwd=ROOT, env=env)
    icu = package / '_internal/icuuc.dll'
    if icu.exists():
        import pefile
        pe = pefile.PE(str(icu), max_symbol_exports=100000)
        exports = {symbol.name for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols}
        if b'ucnv_open' not in exports and (Path(os.environ['SystemRoot']) / 'System32/icuuc.dll').exists():
            shutil.move(str(icu), str(ROOT / 'build' / ('incompatible-icu-' + uuid.uuid4().hex + '.dll')))
    bundle_runtime(package, binaries, ['PySide6-Essentials', 'shiboken6', 'numpy', 'Pillow', 'opencv-python-headless'])
    example = package / 'Exemplo'
    example.mkdir(exist_ok=True)
    for name in ('cenario.png', 'objeto.png', 'video.mp4'):
        shutil.copy2(ROOT / 'demo' / name, example / name)
    data = json.loads((ROOT / 'demo/projeto.json').read_text(encoding='utf-8'))
    data['settings'].update(refine_foreground=True, edge_refinement=3, hole_area=600, feather=0)
    (example / 'exemplo.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    shutil.copy2(ROOT / 'LEIA-ME-APP.md', package / 'LEIA-ME.md')
    verification = ROOT / 'build' / ('desktop-verify-' + uuid.uuid4().hex + '.json')
    subprocess.run([str(package / 'Clean Plate Studio.exe'), '--project', str(example / 'exemplo.json'),
        '--verify-package', str(verification)], env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=True)
    report = json.loads(verification.read_text(encoding='utf-8'))
    if not report.get('success') or not report.get('frozen'):
        raise RuntimeError('Falha na validação do executável: ' + json.dumps(report))
    print(package / 'Clean Plate Studio.exe')


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        build_failure(error)
