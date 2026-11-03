"""RGB-guided alpha refinement, without a learned model or an 8-bit mask.

The local linear model solves the full 3 x 3 RGB covariance system. Coefficients
are estimated at up to 720 pixels on the longest side and evaluated against the
original RGB image, keeping the working set bounded for large video frames.
This improves edge placement; it cannot recover an object absent from the mask.
"""
import math

import numpy as np


def refine_alpha(frame, alpha, radius):
    """Refine float alpha using RGB guide values in [0, 255].

    ``radius`` is measured in pixels of the supplied image. Zero is an identity.
    Opaque/transparent areas beyond the filter support retain their exact value.
    Only NumPy and the core OpenCV package are required, not opencv-contrib.
    """
    radius = float(radius)
    if not math.isfinite(radius) or radius < 0:
        raise ValueError('O raio de refinamento deve ser finito e não negativo')
    source = np.asarray(alpha, dtype=np.float32)
    guide = np.asarray(frame)
    if source.ndim != 2 or guide.shape != source.shape + (3,) or not source.size:
        raise ValueError('RGB e alpha devem ter dimensões correspondentes e não vazias')
    if not np.isfinite(source).all() or not np.isfinite(guide).all():
        raise ValueError('RGB e alpha devem conter valores finitos')
    source = np.clip(source, 0, 1)
    if radius == 0 or np.all(source == 0) or np.all(source == 1):
        return source.copy()

    import cv2

    h, w = source.shape
    scale = min(1., 720. / max(h, w))
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    rgb = np.clip(guide.astype(np.float32) / 255., 0, 1)
    small_rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    small_alpha = cv2.resize(source, size, interpolation=cv2.INTER_AREA) if scale < 1 else source
    small_radius = max(1, math.ceil(radius * scale))
    kernel = (2 * small_radius + 1,) * 2

    def mean(array):
        return cv2.boxFilter(array, -1, kernel, normalize=True, borderType=cv2.BORDER_REFLECT)

    mean_rgb, mean_alpha = mean(small_rgb), mean(small_alpha)
    covariance = np.empty(small_alpha.shape + (3, 3), dtype=np.float32)
    for row in range(3):
        for col in range(row, 3):
            value = mean(small_rgb[..., row] * small_rgb[..., col]) - mean_rgb[..., row] * mean_rgb[..., col]
            if row == col:
                # Regularize the SPD covariance even on flat or gray guides.
                value += .0004
            covariance[..., row, col] = value
            covariance[..., col, row] = value
    cross = mean(small_rgb * small_alpha[..., None]) - mean_rgb * mean_alpha[..., None]
    # Explicit last singleton dimension is compatible with NumPy 1.x and 2.x.
    coefficients = np.linalg.solve(covariance, cross[..., None])[..., 0]
    intercept = mean_alpha - np.sum(coefficients * mean_rgb, axis=2)
    del covariance, cross
    coefficients, intercept = mean(coefficients), mean(intercept)
    if scale < 1:
        coefficients = cv2.resize(coefficients, (w, h), interpolation=cv2.INTER_LINEAR)
        intercept = cv2.resize(intercept, (w, h), interpolation=cv2.INTER_LINEAR)
    result = np.clip(np.sum(coefficients * rgb, axis=2) + intercept, 0, 1).astype(np.float32)

    # A guided filter has support of twice its window radius. Do not allow its
    # numerical error or coarse coefficient interpolation to haze solid regions.
    support = min(max(h, w), max(1, math.ceil(2 * radius)))
    footprint = np.ones((2 * support + 1, 2 * support + 1), np.uint8)
    local_min = cv2.erode(source, footprint, borderType=cv2.BORDER_REPLICATE)
    local_max = cv2.dilate(source, footprint, borderType=cv2.BORDER_REPLICATE)
    result[local_min >= 1.] = 1.
    result[local_max <= 0.] = 0.
    return result
