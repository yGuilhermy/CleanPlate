"""Classical local feature matching. No trained model, inference or network."""
import numpy as np


def estimate_alignment(reference, frame):
    import cv2
    if reference.shape != frame.shape:
        raise ValueError('Redimensione a referência para a resolução do vídeo antes de alinhar.')
    h, w = frame.shape[:2]
    ratio = min(1, 1000/max(h, w))
    size = (round(w*ratio), round(h*ratio))
    first = cv2.cvtColor(cv2.resize(np.uint8(np.clip(reference, 0, 255)), size), cv2.COLOR_RGB2GRAY)
    second = cv2.cvtColor(cv2.resize(frame, size), cv2.COLOR_RGB2GRAY)
    cv2.setRNGSeed(0)
    sift = cv2.SIFT_create(nfeatures=5000, contrastThreshold=.015)
    key1, desc1 = sift.detectAndCompute(first, None)
    key2, desc2 = sift.detectAndCompute(second, None)
    if desc1 is None or desc2 is None:
        raise ValueError('O cenário não tem detalhes suficientes para alinhar automaticamente.')
    matches = cv2.BFMatcher().knnMatch(desc1, desc2, k=2)
    good = [pair[0] for pair in matches if len(pair)==2 and pair[0].distance < .7*pair[1].distance]
    if len(good) < 10:
        raise ValueError('Poucos pontos de fundo correspondentes. Use o alinhamento manual.')
    src = np.float32([key1[item.queryIdx].pt for item in good])
    dst = np.float32([key2[item.trainIdx].pt for item in good])
    matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3)
    count = 0 if inliers is None else int(inliers.sum())
    if matrix is None or count < 10 or count/len(good) < .35:
        raise ValueError('Alinhamento sem confiança suficiente. Use os controles manuais.')
    matrix[:, 2] /= ratio
    a, b = matrix[0, 0], matrix[1, 0]
    scale = float(np.hypot(a, b)*100)
    rotation = float(np.rad2deg(np.arctan2(b, a)))
    cx, cy = (w-1)/2, (h-1)/2
    dx = float(matrix[0, 2]-cx+a*cx-b*cy)
    dy = float(matrix[1, 2]-cy+b*cx+a*cy)
    if not (50 <= scale <= 200 and abs(rotation) <= 15 and abs(dx) <= 500 and abs(dy) <= 500):
        raise ValueError('Transformação muito grande. Confira se a foto corresponde ao mesmo cenário.')
    return {'scale': scale, 'rotation': rotation, 'offset_x': dx, 'offset_y': dy}, count
