"""Small, local UI recognizer. All coordinates refer to the input image."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np


def load_image(path):
    raw = Path(path).read_bytes()
    if not raw:
        raise ValueError("Input image file is empty")
    try:
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as error:
        raise ValueError("Input could not be decoded as an image") from error
    if image is None or image.size == 0:
        raise ValueError("Input is not a readable image")
    if image.shape[0] * image.shape[1] > 32_000_000:
        raise ValueError("Image exceeds 32 megapixels")
    return image


def rectangle(value, width, height):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("Rectangle must be [x, y, width, height]")
    if any(type(n) is not int for n in value):
        raise ValueError("Rectangle coordinates must be integers")
    x, y, w, h = value
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > width or y + h > height:
        raise ValueError("Rectangle is outside the input image")
    return x, y, w, h


def element(kind, label, source, score, box):
    x, y, w, h = map(int, box)
    return {"kind": kind, "label": label, "source": source,
            "score": round(float(score), 5) if score is not None else None,
            "bbox": [x, y, w, h], "center": [x + w // 2, y + h // 2]}


def overlap(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    shared = max(0, x2 - x1) * max(0, y2 - y1)
    return shared / max(1, min(a[2] * a[3], b[2] * b[3]))


def match_template(image, spec, base):
    height, width = image.shape[:2]
    target = load_image(base / spec["path"])
    gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
    if float(gray.std()) < 1.0:
        raise ValueError("Template has too little visual detail")
    x, y, w, h = rectangle(spec.get("roi", [0, 0, width, height]), width, height)
    th, tw = gray.shape
    if tw > w or th > h:
        raise ValueError("Template is larger than its search region")
    threshold = float(spec.get("threshold", 0.9))
    if not 0 < threshold <= 1:
        raise ValueError("Template threshold must be in (0, 1]")
    region = cv2.cvtColor(image[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
    scores = cv2.matchTemplate(region, gray, cv2.TM_CCOEFF_NORMED)
    # Repeated maxima are suppressed only when they overlap the same target.
    found = []
    limit = 50
    for _ in range(limit):
        _, score, _, point = cv2.minMaxLoc(scores)
        if not np.isfinite(score) or score < threshold:
            break
        px, py = point
        box = [x + px, y + py, tw, th]
        if all(overlap(box, hit["bbox"]) < 0.4 for hit in found):
            found.append(element("template", spec["id"], "template", score, box))
        # Remove the neighborhood of this placement; keep distant identical targets.
        sx, sy = max(0, px - tw // 2), max(0, py - th // 2)
        ex, ey = min(scores.shape[1], px + tw // 2 + 1), min(scores.shape[0], py + th // 2 + 1)
        scores[sy:ey, sx:ex] = -1
    truncated = bool(np.max(scores) >= threshold)
    ambiguous = len(found) > 1 or truncated
    for hit in found:
        hit["ambiguous"] = ambiguous
    return found, truncated


def visual_candidates(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        box = list(cv2.boundingRect(contour))
        x, y, w, h = box
        area = cv2.contourArea(contour)
        if w < 20 or h < 12 or w * h > gray.size * 0.85 or area < w * h * 0.6:
            continue
        if all(overlap(box, other) < 0.85 for other in boxes):
            boxes.append(box)
    # These are shapes, not confirmed buttons or clickable objects.
    return [element("visual_candidate", "unknown", "contour", None, b)
            for b in sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)[:100]]


def infer_state(elements, config, warnings):
    state = {"label": "unknown", "evidence_ids": []}
    if config.get("calibrated") is not True or config.get("expected_size") is None:
        warnings.append("uncalibrated: scene remains unknown")
        return state
    texts = [e for e in elements if e["kind"] == "text"]
    matches = []
    for rule in config.get("states", []):
        if not isinstance(rule, dict):
            raise ValueError("State rules must be objects")
        required = rule.get("requires", [])
        phrases = rule.get("all_text", [])
        if (not isinstance(rule.get("name"), str) or not rule["name"]
                or not isinstance(required, list) or not isinstance(phrases, list)
                or any(not isinstance(v, str) or not v.strip() for v in required + phrases)
                or not required and not phrases):
            raise ValueError("State rules need requires or all_text")
        candidates = [e for e in elements if e["kind"] == "template" and e["label"] in required]
        if not all(sum(e["label"] == label for e in candidates) == 1 for label in required):
            continue
        if any(e.get("ambiguous") for e in candidates):
            continue
        phrase_hits = [[e for e in texts if "".join(phrase.split()) in "".join(e["label"].split())]
                       for phrase in phrases]
        if not all(phrase_hits):
            continue
        evidence = candidates + [e for hits in phrase_hits for e in hits]
        matches.append({"label": rule["name"], "evidence_ids": list(dict.fromkeys(e["id"] for e in evidence))})
    if len(matches) == 1:
        return matches[0]
    if matches:
        warnings.append("ambiguous_scene: multiple rules matched")
    return state


def observe(image_path, config_path=None, ocr=False, ocr_reader=None):
    start = time.perf_counter()
    image = load_image(image_path)
    height, width = image.shape[:2]
    config = json.loads(Path(config_path).read_text(encoding="utf-8-sig")) if config_path else {}
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    base = Path(config_path).resolve().parent if config_path else Path.cwd()
    expected = config.get("expected_size")
    if expected is not None and expected != [width, height]:
        raise ValueError("Input dimensions differ from expected_size; recalibration required")
    # Mask before every recognition pass, including templates and the image digest.
    masks = config.get("masks", [])
    for mask in masks:
        x, y, w, h = rectangle(mask, width, height)
        image[y:y + h, x:x + w] = 0
    warnings, elements, groups = [], [], {}
    for spec in config.get("templates", []):
        if not isinstance(spec, dict):
            raise ValueError("Templates must be objects")
        if not isinstance(spec.get("id"), str) or not spec["id"] or spec["id"] in groups:
            raise ValueError("Template IDs must be nonempty and unique")
        hits, truncated = match_template(image, spec, base)
        groups[spec["id"]] = {"count": len(hits), "ambiguous": len(hits) > 1 or truncated}
        if truncated:
            warnings.append(f"template_matches_truncated: {spec['id']}")
        elements.extend(hits)
    if ocr:
        if ocr_reader is None:
            from .ocr import read_ocr
            ocr_reader = read_ocr
        elements.extend(ocr_reader(image, float(config.get("ocr_min_score", 0.5))))
    else:
        warnings.append("ocr_disabled: text content is not recognized")
    if config.get("detect_shapes", True):
        elements.extend(visual_candidates(image))
    # Never emit an element that intersects a masked region.
    elements = [e for e in elements if all(overlap(e["bbox"], m) == 0 for m in masks)]
    for i, item in enumerate(elements):
        item["id"] = f"e{i + 1}"
    # Counts and ambiguity describe the emitted, unmasked candidates only.
    for label, group in groups.items():
        hits = [e for e in elements if e["kind"] == "template" and e["label"] == label]
        truncated = f"template_matches_truncated: {label}" in warnings
        group.update(count=len(hits), ambiguous=len(hits) > 1 or truncated)
        for hit in hits:
            hit["ambiguous"] = group["ambiguous"]
    state = infer_state(elements, config, warnings)
    return {"schema_version": "1.0", "mode": "observation_only",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "image": {"width": width, "height": height,
                      "sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                      "coordinate_space": "input_image_pixels", "source_kind": "file", "masks": masks},
            "state": state, "template_groups": groups, "elements": elements,
            "warnings": warnings, "elapsed_ms": round((time.perf_counter() - start) * 1000, 1)}
