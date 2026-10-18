"""Generate an artificial UI and template, then write an actual observation JSON."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from .recognizer import observe


def generate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    image = np.full((360, 640, 3), (36, 29, 24), np.uint8)
    button = np.full((54, 170, 3), (80, 150, 80), np.uint8)
    cv2.rectangle(button, (0, 0), (169, 53), (180, 230, 180), 2)
    cv2.putText(button, "ENTER GAME", (10, 33), cv2.FONT_HERSHEY_SIMPLEX,
                0.68, (255, 255, 255), 2, cv2.LINE_AA)
    image[250:304, 410:580] = button
    cv2.putText(image, "DEMO CHARACTER", (45, 70), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (235, 235, 235), 2, cv2.LINE_AA)
    cv2.imwrite(str(directory / "frame.png"), image)
    cv2.imwrite(str(directory / "enter.png"), button)
    config = {"calibrated": True, "expected_size": [640, 360],
              "detect_shapes": False, "templates": [
                  {"id": "enter_game", "path": "enter.png", "threshold": 0.99}],
              "states": [{"name": "demo_character_select", "requires": ["enter_game"]}]}
    config_path = directory / "config.local.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    result = observe(directory / "frame.png", config_path)
    (directory / "observation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Artificial read-only UI fixture; not a game run")
    parser.add_argument("--out", type=Path, default=Path("runs/microvision-demo"))
    print(json.dumps(generate(parser.parse_args().out), ensure_ascii=False, indent=2))
