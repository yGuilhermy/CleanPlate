"""Reference-seeded graph cut. Fits colors to this frame only; no trained model."""
import numpy as np


def largest_component(binary):
    import cv2
    count, labels, stats, _ = cv2.connectedComponentsWithStats(np.uint8(binary), connectivity=8)
    if count <= 1:
        return np.zeros(binary.shape, np.uint8)
    return np.uint8(labels == (1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))))


def refine_foreground(frame, distance, alpha, valid, settings):
    """Let image colors/edges resolve uncertain areas of a difference matte.

    Only well-separated, eroded seeds are locked. A low difference alone is NOT a
    certain background pixel: skin/clothing can match the plate. Missing either
    seed class leaves the difference matte unchanged. Work is bounded at 960 px;
    edge refinement can recover a contour at the original resolution afterwards.
    """
    import cv2
    h, w = alpha.shape
    factor = min(1., 960 / max(h, w))
    size = (max(1, round(w * factor)), max(1, round(h * factor)))
    rgb = cv2.resize(np.uint8(np.clip(frame, 0, 255)), size, interpolation=cv2.INTER_AREA)
    diff = cv2.resize(distance, size, interpolation=cv2.INTER_AREA)
    known = cv2.resize(np.uint8(valid), size, interpolation=cv2.INTER_NEAREST) > 0
    threshold, softness = settings.threshold, settings.softness
    mask = np.full(diff.shape, cv2.GC_PR_BGD, np.uint8)
    mask[diff > threshold + softness * .5] = cv2.GC_PR_FGD

    # A generous uncertain band allows similar-colored fingers/arms to recover.
    radius = max(1, round(settings.refine_radius * factor))
    footprint = np.ones((2 * radius + 1, 2 * radius + 1), np.uint8)
    minimum_samples = max(5, round(diff.size * .0002))
    for fraction in (.65, .85, 1.):
        bg = cv2.erode(np.uint8((diff < threshold * fraction) & known), footprint)
        if np.count_nonzero(bg) >= minimum_samples:
            break
    # Photo/video noise can exhaust a stricter seed cutoff. Relax only within
    # the user's background tolerance, retaining the wide spatial safety band.
    fg = np.uint8((diff > threshold + softness * 3) & known)
    fg = cv2.erode(fg, np.ones((5, 5), np.uint8))
    if settings.keep_largest:
        fg = largest_component(fg)
    if np.count_nonzero(bg) < minimum_samples or np.count_nonzero(fg) < 5:
        return alpha.copy()
    mask[bg > 0] = cv2.GC_BGD
    mask[fg > 0] = cv2.GC_FGD
    # Out-of-photo pixels have no evidence for removal; preserve legacy policy.
    mask[~known] = cv2.GC_FGD
    cv2.setRNGSeed(0)
    cv2.grabCut(rgb, mask, None, np.zeros((1, 65), np.float64),
                np.zeros((1, 65), np.float64), 3, cv2.GC_INIT_WITH_MASK)
    result = np.float32((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD))
    return cv2.resize(result, (w, h), interpolation=cv2.INTER_LINEAR)


def fill_small_holes(alpha, max_area):
    """Fill enclosed components only, never border-connected background.

    The area limit is in source pixels. Large genuine openings (e.g. a headset
    arch) survive. Very small genuine openings may also fill: this is optional.
    """
    import cv2
    if max_area <= 0:
        return alpha
    bg = np.uint8(alpha < .5)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(bg, connectivity=8)
    allowed = stats[:, cv2.CC_STAT_AREA] <= max_area
    allowed[0] = False
    boundary = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    allowed[boundary] = False
    result = alpha.copy()
    result[allowed[labels]] = 1
    return result
