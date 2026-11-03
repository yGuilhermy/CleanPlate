"""Pure preview computation; called off the UI thread with an immutable snapshot."""
from dataclasses import replace
import numpy as np
from PIL import Image
from .engine import Background, matte, composite, checker_preview, flatten_rgba, blurred_background


def calculate(frame, background, settings, view, backdrop, limit=1440):
    if background is not None and background.mean.shape != frame.shape:
        raise ValueError('Clipe e referência têm resoluções diferentes. Carregue uma referência compatível.')
    h, w = frame.shape[:2]
    factor = min(1, limit / max(h, w))
    if factor < 1:
        size = (round(w * factor), round(h * factor))
        frame = np.asarray(Image.fromarray(frame).resize(size, Image.Resampling.BILINEAR))
        if background is not None:
            def resize(array):
                return np.stack([np.asarray(Image.fromarray(array[..., i]).resize(size, Image.Resampling.BILINEAR))
                                 for i in range(3)], axis=2)
            background = Background(resize(background.mean), resize(background.deviation), background.samples)
        changes = {name: getattr(settings, name) * factor for name in
                   ('offset_x', 'offset_y', 'feather', 'shadow_blur', 'glow_blur', 'edge_refinement', 'background_blur')}
        changes['refine_radius'] = max(1, settings.refine_radius * factor)
        changes['hole_area'] = round(settings.hole_area * factor * factor)
        changes.update({name: round(getattr(settings, name) * factor)
                        for name in ('expand', 'outline', 'shadow_x', 'shadow_y')})
        settings = replace(settings, **changes)
    if background is None or view == 'Original':
        return frame, None
    alpha, distance = matte(frame, background, settings)
    rgba = composite(frame, alpha, settings)
    if view == 'Matte':
        result = np.repeat(np.uint8(alpha[..., None] * 255), 3, axis=2)
    elif view == 'Diferença':
        result = np.repeat(np.uint8(np.clip(distance[..., None] * 3, 0, 255)), 3, axis=2)
    else:
        colors = {'Escuro': (20, 25, 32), 'Claro': (235, 238, 242), 'Verde': (36, 185, 92)}
        if backdrop == 'Desfocado':
            result = blurred_background(frame, rgba, background, settings)
        elif backdrop.startswith('#'):
            result = flatten_rgba(rgba, backdrop)
        elif backdrop in colors:
            a = rgba[..., 3:4].astype(np.float32) / 255
            result = np.uint8(rgba[..., :3] * a + np.asarray(colors[backdrop]) * (1 - a))
        else:
            result = checker_preview(rgba)
        if view == 'Comparar':
            result[:, :result.shape[1] // 2] = frame[:, :result.shape[1] // 2]
            result[:, result.shape[1] // 2] = (240, 240, 240)
    return result, rgba
