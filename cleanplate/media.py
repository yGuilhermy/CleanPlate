"""Local media I/O. No shell, service, AI model or network is used."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import uuid
import sys
from fractions import Fraction
import numpy as np
from PIL import Image, ImageOps
from .engine import Background, matte, composite, flatten_rgba, blurred_background

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp'}
CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


class Cancelled(Exception):
    pass


def executable(name):
    if getattr(sys, 'frozen', False):
        bundled = Path(sys.executable).parent / 'bin' / (name + '.exe')
        if bundled.is_file():
            return str(bundled)
    value = shutil.which(name)
    if not value:
        raise RuntimeError(f'{name} não encontrado. Instale FFmpeg e adicione ao PATH.')
    return value


def run(args):
    result = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL, creationflags=CREATE_FLAGS)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-4000:])
    return result.stdout


def is_image(path):
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def probe(path):
    if is_image(path):
        with Image.open(path) as im:
            w, h = ImageOps.exif_transpose(im).size
        return {'width': w, 'height': h, 'fps': '1', 'duration': 0.0, 'image': True}
    data = json.loads(run([executable('ffprobe'), '-v', 'error', '-show_streams',
                           '-show_format', '-of', 'json', str(path)]))
    streams = [s for s in data['streams'] if s['codec_type'] == 'video'
               and not s.get('disposition', {}).get('attached_pic')]
    if not streams:
        raise ValueError('Arquivo não contém vídeo')
    stream = streams[0]
    if stream.get('color_transfer') in ('smpte2084', 'arib-std-b67'):
        raise ValueError('Esta versão trabalha em SDR. Converta HDR para Rec.709 antes de abrir.')
    # FFmpeg autorotation is enabled consistently for preview and export decoding.
    rotation = float(stream.get('tags', {}).get('rotate', 0))
    for side in stream.get('side_data_list', []):
        rotation = float(side.get('rotation', rotation))
    normalized_rotation = round(rotation) % 360
    if normalized_rotation not in (0, 90, 180, 270):
        raise ValueError('Rotação de vídeo não ortogonal: normalize antes de abrir.')
    width, height = stream['width'], stream['height']
    if normalized_rotation in (90, 270):
        width, height = height, width
    fps = stream.get('avg_frame_rate', '0/0')
    if fps == '0/0' or Fraction(fps) <= 0:
        fps = stream.get('r_frame_rate', '30/1')
    duration = float(stream.get('duration', data.get('format', {}).get('duration', 0)))
    return {'width': width, 'height': height, 'fps': fps,
            'duration': duration, 'image': False, 'rotation': normalized_rotation}


def read_frame(path, seconds=0, info=None):
    info = info or probe(path)
    if info['image']:
        with Image.open(path) as im:
            return np.asarray(ImageOps.exif_transpose(im).convert('RGB')).copy()
    raw = run([executable('ffmpeg'), '-v', 'error', '-ss', str(seconds),
               '-i', str(path), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'])
    expected = info['width'] * info['height'] * 3
    if len(raw) != expected:
        raise ValueError('Não foi possível ler o frame nessa posição')
    return np.frombuffer(raw, np.uint8).reshape(info['height'], info['width'], 3).copy()


def build_background(path, start=0, duration=3, samples=24, cancel=None, progress=None):
    info = probe(path)
    if info['image']:
        return Background.from_frames([read_frame(path, info=info)])
    if start < 0 or duration <= 0 or samples < 2:
        raise ValueError('Intervalo de referência inválido')
    if start >= info['duration']:
        raise ValueError('Início da referência está depois do fim do vídeo')
    end = min(start + duration, max(start, info['duration'] - 1 / float(Fraction(info['fps']))))

    def frames():
        for index, time in enumerate(np.linspace(start, end, samples)):
            if cancel and cancel.is_set():
                raise Cancelled()
            yield read_frame(path, float(time), info)
            if progress:
                progress((index + 1) / samples)
    return Background.from_frames(frames())


def _read_exact(pipe, size):
    chunks = bytearray()
    while len(chunks) < size:
        part = pipe.read(size - len(chunks))
        if not part:
            break
        chunks.extend(part)
    return chunks


def export_video(source, destination, background, settings, mode='cutout', cancel=None, progress=None,
                 background_color='#000000', quality=18, audio=True):
    settings.validate()
    info = probe(source)
    if info['image']:
        raise ValueError('Use exportação PNG para imagens')
    destination = Path(destination)
    expected_suffix = '.mov' if mode == 'cutout' else '.mp4'
    if mode not in ('cutout', 'matte', 'solid', 'blur') or destination.suffix.lower() != expected_suffix:
        raise ValueError(f'Formato esperado: {expected_suffix}')
    if mode == 'solid':
        from PIL import ImageColor
        if len(ImageColor.getrgb(background_color)) != 3:
            raise ValueError('Escolha uma cor RGB sem transparência')
    if quality not in range(0, 52):
        raise ValueError('Qualidade de vídeo inválida')
    if destination.resolve() == Path(source).resolve():
        raise ValueError('A saída não pode substituir o vídeo original')
    h, w = info['height'], info['width']
    if background.mean.shape != (h, w, 3):
        raise ValueError('Vídeo e referência precisam ter a mesma resolução')
    ffmpeg = executable('ffmpeg')
    cancel = cancel or threading.Event()
    temp = destination.with_name(destination.stem + '.' + uuid.uuid4().hex + '.partial' + expected_suffix)
    decoder = encoder = None
    stop = threading.Event()
    processes = []

    def watch_cancel():
        while not stop.wait(.1):
            if cancel.is_set():
                for process in list(processes):
                    if process.poll() is None:
                        process.terminate()
                return

    watcher = threading.Thread(target=watch_cancel, daemon=True)
    watcher.start()
    try:
        with tempfile.TemporaryFile() as decode_log, tempfile.TemporaryFile() as encode_log:
            decoder = subprocess.Popen([ffmpeg, '-nostdin', '-v', 'error', '-i', str(source),
                '-map', '0:v:0', '-vf', 'fps=' + info['fps'], '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=decode_log, creationflags=CREATE_FLAGS)
            processes.append(decoder)
            args = [ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba',
                    '-s', f'{w}x{h}', '-r', info['fps'], '-i', 'pipe:0']
            if mode != 'matte' and audio:
                args += ['-i', str(source), '-map', '0:v:0', '-map', '1:a:0?']
            if mode == 'cutout':
                args += ['-c:v', 'prores_ks', '-profile:v', '4', '-pix_fmt', 'yuva444p10le',
                         '-vf', 'scale=in_range=full:out_range=tv:out_color_matrix=bt709',
                         '-alpha_bits', '16']
                args += ['-c:a', 'pcm_s16le', '-t', str(info['duration'])] if audio else ['-an']
            else:
                args += ['-c:a', 'aac', '-b:a', '192k', '-t', str(info['duration'])] if mode in ('solid', 'blur') and audio else ['-an']
                args += ['-c:v', 'libx264', '-crf', str(quality), '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                         '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2,scale=in_range=full:out_range=tv:out_color_matrix=bt709']
            # RGB input is converted by FFmpeg to Rec.709 video levels.
            args += ['-colorspace', 'bt709', '-color_primaries', 'bt709',
                     '-color_trc', 'bt709', str(temp)]
            encoder = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=encode_log,
                                       creationflags=CREATE_FLAGS)
            processes.append(encoder)
            count = 0
            try:
                while True:
                    if cancel.is_set():
                        raise Cancelled()
                    raw = _read_exact(decoder.stdout, w * h * 3)
                    if not raw:
                        break
                    if len(raw) != w * h * 3:
                        raise RuntimeError('Frame incompleto na leitura')
                    frame = np.frombuffer(raw, np.uint8).reshape(h, w, 3)
                    alpha, _ = matte(frame, background, settings)
                    if mode in ('cutout', 'solid', 'blur'):
                        result = composite(frame, alpha, settings)
                        if mode == 'solid':
                            rgb = flatten_rgba(result, background_color)
                            result = np.dstack((rgb, np.full((h, w), 255, dtype=np.uint8)))
                        elif mode == 'blur':
                            rgb = blurred_background(frame, result, background, settings)
                            result = np.dstack((rgb, np.full((h, w), 255, dtype=np.uint8)))
                    else:
                        gray = np.uint8(np.rint(alpha * 255))
                        result = np.dstack((gray, gray, gray, np.full_like(gray, 255)))
                    encoder.stdin.write(result.tobytes())
                    count += 1
                    if progress:
                        progress(min(count / max(info['duration'] * float(Fraction(info['fps'])), 1), .99))
                encoder.stdin.close()
                decoder.wait()
                encoder.wait()
                if cancel.is_set():
                    raise Cancelled()
                if decoder.returncode or encoder.returncode or not count:
                    raise RuntimeError('FFmpeg não concluiu a exportação')
            except (BrokenPipeError, RuntimeError) as exc:
                if cancel.is_set():
                    raise Cancelled() from exc
                encode_log.seek(0)
                decode_log.seek(0)
                details = (encode_log.read() + decode_log.read()).decode('utf-8', errors='replace')
                raise RuntimeError(f'{exc}\n{details[-4000:]}') from exc
        if cancel.is_set():
            raise Cancelled()
        os.replace(temp, destination)
        if progress:
            progress(1)
        return count
    finally:
        stop.set()
        watcher.join(timeout=1)
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.wait()
            for stream in (process.stdin, process.stdout):
                if stream and not stream.closed:
                    try:
                        stream.close()
                    except OSError:
                        pass
        temp.unlink(missing_ok=True)
