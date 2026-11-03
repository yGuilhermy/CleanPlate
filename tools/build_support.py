import importlib.metadata
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def prepare(modules):
    if os.name != 'nt':
        raise SystemExit('Os pacotes portáteis são compilados no Windows.')
    deps = ROOT / '.deps'
    if deps.is_dir():
        sys.path.insert(0, str(deps))
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    if missing:
        raise SystemExit('Dependências ausentes: ' + ', '.join(missing) +
                         '. Execute: python -m pip install -r requirements-build.txt')
    binaries = {name: shutil.which(name) for name in ('ffmpeg', 'ffprobe')}
    if not all(binaries.values()):
        raise SystemExit('FFmpeg/FFprobe ausentes no PATH. Instale em https://ffmpeg.org/download.html')
    (ROOT / 'build').mkdir(exist_ok=True)
    windows = Path(os.environ['SystemRoot'])
    paths = [Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / 'DLLs',
             windows / 'System32', windows]
    if 'PySide6' in modules:
        paths.insert(0, Path(next(iter(importlib.util.find_spec('PySide6').submodule_search_locations))))
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join([str(deps), str(ROOT), env.get('PYTHONPATH', '')])
    env['PATH'] = os.pathsep.join(map(str, paths))
    return env, {name: Path(path).resolve() for name, path in binaries.items()}


def check_destination(package, executable):
    target = package / executable
    if target.is_file():
        try:
            with target.open('r+b'):
                pass
        except PermissionError as error:
            raise RuntimeError('Feche o aplicativo antes de substituir o pacote, ou escolha outra pasta de saída.') from error


def bundle_runtime(package, binaries, distributions):
    (package / 'bin').mkdir(exist_ok=True)
    licenses = package / 'licenses'
    licenses.mkdir(exist_ok=True)
    for name, source in binaries.items():
        shutil.copy2(source, package / 'bin' / (name + '.exe'))
    for name in ('LICENSE', 'THIRD_PARTY.md'):
        shutil.copy2(ROOT / name, package / name)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        shutil.copy2(python_license, licenses / 'Python-LICENSE.txt')
    pending = list(distributions) + ['pyinstaller']
    visited = set()
    versions = {}
    while pending:
        name = pending.pop()
        normalized = name.lower().replace('_', '-')
        if normalized in visited:
            continue
        visited.add(normalized)
        distribution = importlib.metadata.distribution(name)
        versions[distribution.metadata['Name']] = distribution.version
        from packaging.requirements import Requirement
        for specification in distribution.requires or []:
            requirement = Requirement(specification)
            if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                pending.append(requirement.name)
        for item in distribution.files or []:
            if '.dist-info/' in str(item).replace('\\', '/') and any(
                part.lower() in ('license', 'licenses', 'license.txt', 'license.md', 'copying') for part in item.parts
            ):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    target = licenses / name / Path(*item.parts[1:])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    for name in ('LICENSE', 'LICENSE.txt', 'LICENSE.md'):
        source = binaries['ffmpeg'].parents[1] / name
        if source.is_file():
            shutil.copy2(source, licenses / ('FFmpeg-' + name))
    runtime = {'python': sys.version.split()[0], 'distributions': dict(sorted(versions.items())), 'binaries': {}}
    for name in binaries:
        binary = package / 'bin' / (name + '.exe')
        result = subprocess.run([str(binary), '-version'], capture_output=True, check=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        with binary.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        runtime['binaries'][name] = {'sha256': digest,
                                    'version': result.stdout.decode('utf-8', errors='replace').splitlines()}
    (licenses / 'runtime.json').write_text(json.dumps(runtime, indent=2), encoding='utf-8')


def build_failure(error):
    raise SystemExit('Falha ao gerar o pacote. Feche o aplicativo se os arquivos estiverem em uso. ' + str(error))
