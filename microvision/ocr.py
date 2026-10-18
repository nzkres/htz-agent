"""Local CPU OCR only; returns observations and never sends input or saves images."""
from functools import lru_cache

import numpy as np


@lru_cache(maxsize=1)
def _engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as error:
        raise RuntimeError(
            "Local OCR dependency missing: install rapidocr_onnxruntime==1.4.4. "
            "No API key is needed."
        ) from error
    try:
        return RapidOCR(det_use_cuda=False, cls_use_cuda=False, rec_use_cuda=False,
                        det_use_dml=False, cls_use_dml=False, rec_use_dml=False)
    except Exception as error:
        raise RuntimeError("Local OCR model initialization failed; check the installed models.") from error


def read_ocr(image: np.ndarray, min_confidence=0.5) -> list[dict]:
    """Read a nonempty uint8 BGR image; bbox uses [x, y, width, height]."""
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("OCR input must be a BGR numpy array with three channels.")
    if image.dtype != np.uint8 or image.shape[0] == 0 or image.shape[1] == 0:
        raise ValueError("OCR input must be a nonempty uint8 BGR image.")
    threshold = float(min_confidence)
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("min_confidence must be between 0 and 1.")
    engine = _engine()
    try:
        rows, _ = engine(np.ascontiguousarray(image), text_score=threshold)
    except Exception as error:
        raise RuntimeError("Local OCR inference failed; no cloud API is used.") from error
    if rows is None:
        return []
    height, width = image.shape[:2]
    observations = []
    try:
        for polygon, label, confidence in rows:
            score = float(confidence)
            points = np.asarray(polygon, dtype=float)
            if points.shape != (4, 2) or not np.isfinite(points).all():
                raise ValueError("Invalid OCR polygon.")
            if not isinstance(label, str) or not np.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Invalid OCR text or confidence.")
            if score < threshold or not label.strip():
                continue
            x, y = np.floor(points.min(axis=0)).astype(int)
            right, bottom = np.ceil(points.max(axis=0)).astype(int)
            x, right = int(np.clip(x, 0, width)), int(np.clip(right, 0, width))
            y, bottom = int(np.clip(y, 0, height)), int(np.clip(bottom, 0, height))
            w, h = right - x, bottom - y
            if w > 0 and h > 0:
                observations.append(dict(kind="text", label=label, source="ocr", score=score,
                                         bbox=[x, y, w, h], center=[x + w // 2, y + h // 2]))
    except Exception as error:
        raise RuntimeError("Local OCR returned an invalid result format.") from error
    return observations
