from dataclasses import dataclass, asdict
import numpy as np
from PIL import Image, ImageFilter


@dataclass
class Settings:
    threshold: float = 20.0
    softness: float = 18.0
    noise: float = 2.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale: float = 100.0
    rotation: float = 0.0
    expand: int = 0
    feather: float = 1.0
    cleanup: int = 0
    compensate_light: bool = False
    outline: int = 0
    outline_color: str = "#ffffff"
    shadow: float = 0.0
    shadow_blur: float = 8.0
    shadow_x: int = 8
    shadow_y: int = 8
    glow: float = 0.0
    glow_blur: float = 12.0
    outline_enabled: bool = True
    shadow_enabled: bool = True
    glow_enabled: bool = True
    extrapolate_reference: bool = False
    keep_largest: bool = False
    fill_holes: bool = False
    refine_foreground: bool = False
    refine_radius: float = 40.0
    edge_refinement: float = 0.0
    hole_area: int = 0
    background_blur: float = 24.0

    def validate(self):
        bounds = {"threshold": (0, 255), "softness": (0.01, 255), "noise": (0, 10),
                  "offset_x": (-8192, 8192), "offset_y": (-8192, 8192),
                  "scale": (50, 200), "rotation": (-180, 180), "expand": (-30, 30),
                  "feather": (0, 30), "cleanup": (0, 5), "outline": (0, 30),
                  "shadow": (0, 1), "shadow_blur": (0, 50), "shadow_x": (-300, 300),
                  "shadow_y": (-300, 300), "glow": (0, 1), "glow_blur": (0, 50),
                  "refine_radius": (1, 100), "edge_refinement": (0, 20), "hole_area": (0, 20000),
                  "background_blur": (0, 100)}
        for name, (lo, hi) in bounds.items():
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not np.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f"Valor inválido: {name} ({lo} a {hi})")
        for name in ("expand", "cleanup", "outline", "shadow_x", "shadow_y", "hole_area"):
            if int(getattr(self, name)) != getattr(self, name):
                raise ValueError(f"{name} deve ser inteiro")
        from PIL import ImageColor
        ImageColor.getrgb(self.outline_color)
        for name in ('outline_enabled', 'shadow_enabled', 'glow_enabled', 'compensate_light', 'extrapolate_reference', 'keep_largest', 'fill_holes', 'refine_foreground'):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f'{name} deve ser verdadeiro ou falso')
        return self

    def to_dict(self):
        return asdict(self)


@dataclass
class Background:
    mean: np.ndarray
    deviation: np.ndarray
    samples: int = 1

    @classmethod
    def from_frames(cls, frames):
        # Online statistics: bounded memory even for a 4K reference take.
        mean = variance = None
        count = 0
        for frame in frames:
            x = np.asarray(frame, dtype=np.float32)
            if x.ndim != 3 or x.shape[2] != 3:
                raise ValueError("Referência deve ter três canais RGB")
            if mean is None:
                mean, variance = x.copy(), np.zeros_like(x)
            else:
                if x.shape != mean.shape:
                    raise ValueError("Frames de referência têm tamanhos diferentes")
                delta = x - mean
                mean += delta / (count + 1)
                variance += delta * (x - mean)
            count += 1
        if not count:
            raise ValueError("Referência vazia")
        return cls(mean, np.sqrt(variance / max(count - 1, 1)), count)


def _transform(array, settings, size, resample=Image.Resampling.BILINEAR, extrapolate=False):
    w, h = size
    angle = np.deg2rad(settings.rotation)
    scale = settings.scale / 100
    a, b = np.cos(angle) / scale, np.sin(angle) / scale
    cx, cy = (w - 1) / 2, (h - 1) / 2
    tx, ty = cx + settings.offset_x, cy + settings.offset_y
    coeff = (a, b, cx - a * tx - b * ty,
             -b, a, cy + b * tx - a * ty)
    if extrapolate:
        import cv2
        return cv2.warpAffine(array.astype(np.float32), np.asarray(coeff, np.float32).reshape(2, 3), size,
                              flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
    if array.ndim == 2:
        return np.asarray(Image.fromarray(array.astype(np.float32)).transform(
            size, Image.Transform.AFFINE, coeff, resample=resample), dtype=np.float32)
    return np.stack([_transform(array[..., i], settings, size, resample)
                     for i in range(3)], axis=2)


def matte(frame, background, settings):
    settings.validate()
    frame = np.asarray(frame, dtype=np.float32)
    if frame.shape != background.mean.shape:
        raise ValueError("Vídeo e referência precisam ter a mesma resolução. Use o mesmo enquadramento.")
    h, w = frame.shape[:2]
    identity = (settings.offset_x == settings.offset_y == settings.rotation == 0 and settings.scale == 100)
    if identity:
        plate, sigma = background.mean, background.deviation
        valid = np.ones((h, w), dtype=bool)
    else:
        plate = _transform(background.mean, settings, (w, h), extrapolate=settings.extrapolate_reference)
        sigma = _transform(background.deviation, settings, (w, h), extrapolate=settings.extrapolate_reference)
        valid = (np.ones((h, w), dtype=bool) if settings.extrapolate_reference else
                 _transform(np.ones((h, w), np.float32), settings, (w, h)) > .99)
    if settings.compensate_light and valid.any():
        plate = compensate_light(frame, plate, valid)
    residual = np.maximum(np.abs(frame - plate) - settings.noise * sigma, 0)
    distance = np.sqrt(np.mean(residual * residual, axis=2))
    t = np.clip((distance - settings.threshold) / settings.softness, 0, 1)
    alpha = t * t * (3 - 2 * t)
    alpha[~valid] = 1
    if settings.refine_foreground:
        from .segmentation import refine_foreground
        alpha = refine_foreground(frame, distance, alpha, valid, settings)
    if settings.keep_largest or settings.fill_holes:
        import cv2
        binary = np.uint8(alpha > .5)
        if settings.keep_largest and binary.any():
            count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
            largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            binary = np.uint8(labels == largest)
            allowed = cv2.dilate(binary, np.ones((3, 3), np.uint8))
            alpha *= allowed
        if settings.fill_holes:
            padded = np.pad(binary, 1)
            flooded = padded.copy()
            cv2.floodFill(flooded, None, (0, 0), 1)
            holes = (flooded[1:-1, 1:-1] == 0) & (binary == 0)
            alpha[holes] = 1
    if settings.hole_area:
        from .segmentation import fill_small_holes
        alpha = fill_small_holes(alpha, settings.hole_area)
    # Preserve float alpha until an explicit morphology/blur operation needs an
    # image. Guided refinement should not quantize the contour before compositing.
    if settings.cleanup or settings.expand or settings.feather:
        image = Image.fromarray(np.uint8(np.rint(alpha * 255)))
        if settings.cleanup:
            image = image.filter(ImageFilter.MedianFilter(2 * int(settings.cleanup) + 1))
        if settings.expand:
            kernel = 2 * abs(int(settings.expand)) + 1
            image = image.filter((ImageFilter.MaxFilter if settings.expand > 0 else ImageFilter.MinFilter)(kernel))
        if settings.feather:
            image = image.filter(ImageFilter.GaussianBlur(settings.feather))
        alpha = np.asarray(image, dtype=np.float32) / 255
    if settings.edge_refinement:
        from .edges import refine_alpha
        alpha = refine_alpha(frame, alpha, settings.edge_refinement)
    return alpha, distance


def compensate_light(frame, plate, valid):
    """Robust color calibration on neutral bright surfaces, without a subject model.

    A median over the entire frame becomes biased when the subject occupies most of
    the view. Neutral wall/ceiling candidates avoid that failure in indoor footage.
    The conservative fallback remains available for scenes without neutral surfaces.
    """
    step = max(1, round(max(frame.shape[:2]) / 400))
    source, target = plate[::step, ::step], frame[::step, ::step]
    mask = valid[::step, ::step].copy()
    mask &= (np.ptp(source, axis=2) < 40) & (np.ptp(target, axis=2) < 40)
    mask &= (source.mean(axis=2) > 80) & (target.mean(axis=2) > 80)
    if mask.sum() < 100:
        delta = np.median((frame-plate)[valid], axis=0)
        return np.clip(plate + np.clip(delta, -80, 80), 0, 255)
    x, y = source[mask], target[mask]
    keep = np.ones(len(x), dtype=bool)
    gain = np.ones(3, dtype=np.float32)
    bias = np.zeros(3, dtype=np.float32)
    for _ in range(4):
        for channel in range(3):
            xx, yy = x[keep, channel], y[keep, channel]
            variance = np.var(xx)
            gain[channel] = np.clip(np.mean((xx-xx.mean())*(yy-yy.mean())) / max(float(variance), 25), .65, 1.6) if variance > 25 else 1
            bias[channel] = np.clip(np.median(yy-gain[channel]*xx), -100, 100)
        error = np.sqrt(np.mean((x*gain+bias-y)**2, axis=1))
        keep = error <= max(6, float(np.percentile(error, 65)))
    return np.clip(plate * gain + bias, 0, 255)


def _blur(alpha, radius):
    return np.asarray(Image.fromarray(np.uint8(np.clip(alpha * 255, 0, 255))).filter(
        ImageFilter.GaussianBlur(radius)), dtype=np.float32) / 255


def _shift(alpha, dx, dy):
    h, w = alpha.shape
    result = np.zeros_like(alpha)
    dx, dy = int(dx), int(dy)
    if abs(dx) < w and abs(dy) < h:
        result[max(dy, 0):min(h + dy, h), max(dx, 0):min(w + dx, w)] = alpha[
            max(-dy, 0):min(h - dy, h), max(-dx, 0):min(w - dx, w)]
    return result


def composite(frame, alpha, settings):
    from PIL import ImageColor
    color = np.asarray(ImageColor.getrgb(settings.outline_color), np.float32) / 255
    h, w = alpha.shape
    rgb = np.zeros((h, w, 3), np.float32)
    a = np.zeros_like(alpha)

    def over(c, opacity):
        nonlocal rgb, a
        rgb = c * opacity[..., None] + rgb * (1 - opacity[..., None])
        a = opacity + a * (1 - opacity)

    if settings.shadow_enabled and settings.shadow:
        over(np.zeros(3), _shift(_blur(alpha, settings.shadow_blur), settings.shadow_x, settings.shadow_y) * settings.shadow)
    if settings.glow_enabled and settings.glow:
        over(color, _blur(alpha, settings.glow_blur) * settings.glow)
    if settings.outline_enabled and settings.outline:
        dilated = np.asarray(Image.fromarray(np.uint8(alpha * 255)).filter(
            ImageFilter.MaxFilter(2 * int(settings.outline) + 1)), dtype=np.float32) / 255
        over(color, np.maximum(dilated - alpha, 0))
    over(np.asarray(frame, np.float32) / 255, alpha)
    # Output straight alpha, with zero RGB in fully transparent pixels.
    straight = np.divide(rgb, a[..., None], out=np.zeros_like(rgb), where=a[..., None] > 1e-6)
    return np.uint8(np.rint(np.clip(np.dstack((straight, a)), 0, 1) * 255))


def checker_preview(rgba):
    h, w = rgba.shape[:2]
    yy, xx = np.indices((h, w))
    grid = np.where(((xx // 20 + yy // 20) % 2)[..., None], 70, 105)
    a = rgba[..., 3:4].astype(np.float32) / 255
    return np.uint8(rgba[..., :3] * a + grid * (1 - a))


def flatten_rgba(rgba, color='#000000'):
    """Composite straight RGBA onto an opaque color, shared by preview and export."""
    from PIL import ImageColor
    background = np.asarray(ImageColor.getrgb(color), dtype=np.float32)
    if background.shape != (3,):
        raise ValueError('Escolha uma cor RGB sem transparência')
    alpha = rgba[..., 3:4].astype(np.float32) / 255
    return np.uint8(np.rint(np.clip(rgba[..., :3] * alpha + background * (1 - alpha), 0, 255)))


def blurred_background(frame, rgba, background, settings):
    """Blur the scene behind the cutout; use the plate to avoid a subject halo."""
    frame = np.asarray(frame, np.float32)
    h, w = frame.shape[:2]
    alpha = rgba[..., 3:4].astype(np.float32) / 255
    scene = frame
    if settings.background_blur > 0:
        plate = _transform(background.mean, settings, (w, h),
                           extrapolate=settings.extrapolate_reference)
        valid = (np.ones((h,w), bool) if settings.extrapolate_reference else
                 _transform(np.ones((h,w), np.float32), settings, (w,h)) > .99)
        if settings.compensate_light and valid.any():
            plate = compensate_light(frame, plate, valid)
        plate = np.where(valid[..., None], plate, frame)
        scene = frame * (1-alpha) + plate * alpha
        scene = np.asarray(Image.fromarray(np.uint8(np.rint(np.clip(scene,0,255)))).filter(
            ImageFilter.GaussianBlur(settings.background_blur)), np.float32)
    return np.uint8(np.rint(np.clip(rgba[..., :3]*alpha + scene*(1-alpha), 0, 255)))
