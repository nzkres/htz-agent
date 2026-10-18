"""Usage: python -m microvision IMAGE [--config FILE] [--ocr] [--output FILE]."""
import argparse
import json
import sys
from pathlib import Path

from .recognizer import observe


def main():
    parser = argparse.ArgumentParser(description="Local read-only UI image to JSON")
    parser.add_argument("image", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--ocr", action="store_true", help="Enable local Chinese/English OCR")
    parser.add_argument("--output", type=Path, help="Optional local JSON path; default stdout only")
    args = parser.parse_args()
    try:
        result = observe(args.image, args.config, args.ocr)
        code = 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        result = {"schema_version": "1.0", "mode": "observation_only",
                  "state": {"label": "unknown", "evidence_ids": []},
                  "elements": [], "error": str(error)}
        code = 2
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        except OSError as error:
            result = {"schema_version": "1.0", "mode": "observation_only",
                      "state": {"label": "unknown", "evidence_ids": []},
                      "elements": [], "error": f"Could not write output: {error}"}
            payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            code = 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
