"""Recognition contracts using synthetic scenes only; no game or input access."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from microvision.recognizer import observe


class ObserveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="microvision-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rng = np.random.default_rng(2081)
        self.patch = self.rng.integers(0, 256, (13, 17, 3), dtype=np.uint8)
        self.write_image("target.png", self.patch)

    def write_image(self, name, pixels):
        path = self.root / name
        ok, encoded = cv2.imencode(".png", pixels)
        self.assertTrue(ok)
        path.write_bytes(encoded.tobytes())
        return path

    def scene(self, width=100, height=80):
        return self.rng.integers(0, 256, (height, width, 3), dtype=np.uint8)

    def config(self, **overrides):
        value = {
            "expected_size": [100, 80],
            "calibrated": True,
            "detect_shapes": False,
            "templates": [{"id": "target", "path": "target.png", "threshold": 0.99}],
            "states": [{"name": "ready", "requires": ["target"]}],
        }
        value.update(overrides)
        path = self.root / "config.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def run_scene(self, pixels, **config):
        path = self.write_image("合成画面.png", pixels)
        return observe(path, self.config(**config))

    @staticmethod
    def template_hits(result):
        return [item for item in result["elements"] if item["kind"] == "template"]

    def test_nonzero_roi_preserves_absolute_coordinates_at_bottom_right_edge(self):
        pixels = self.scene()
        pixels[67:80, 83:100] = self.patch
        result = self.run_scene(pixels, templates=[{
            "id": "target", "path": "target.png", "threshold": 0.99,
            "roi": [61, 41, 39, 39],
        }])
        hits = self.template_hits(result)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["bbox"], [83, 67, 17, 13])
        self.assertEqual(hits[0]["center"], [91, 73])
        self.assertFalse(hits[0]["ambiguous"])
        self.assertEqual(result["image"]["coordinate_space"], "input_image_pixels")
        self.assertEqual(result["state"]["label"], "ready")
        self.assertEqual(result["state"]["evidence_ids"], [hits[0]["id"]])

    def test_roi_does_not_match_identical_target_outside_search_region(self):
        pixels = self.scene()
        pixels[0:13, 0:17] = self.patch
        result = self.run_scene(pixels, templates=[{
            "id": "target", "path": "target.png", "threshold": 0.99,
            "roi": [40, 30, 60, 50],
        }])
        self.assertEqual(self.template_hits(result), [])
        self.assertEqual(result["template_groups"]["target"]["count"], 0)
        self.assertEqual(result["state"]["label"], "unknown")

    def test_two_separate_identical_targets_remain_ambiguous(self):
        pixels = self.scene()
        pixels[0:13, 0:17] = self.patch
        pixels[48:61, 69:86] = self.patch
        result = self.run_scene(pixels)
        hits = self.template_hits(result)
        self.assertEqual({tuple(item["bbox"]) for item in hits},
                         {(0, 0, 17, 13), (69, 48, 17, 13)})
        self.assertTrue(all(item["ambiguous"] for item in hits))
        self.assertEqual(result["template_groups"]["target"]["count"], 2)
        self.assertTrue(result["template_groups"]["target"]["ambiguous"])
        self.assertEqual(result["state"]["label"], "unknown")

    def test_nearby_correlated_matches_are_one_physical_target(self):
        yy, xx = np.mgrid[-8:9, -11:12]
        gray = np.rint(240 * np.exp(-((xx / 6) ** 2 + (yy / 4) ** 2))).astype(np.uint8)
        patch = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        self.write_image("smooth.png", patch)
        pixels = np.zeros((80, 100, 3), dtype=np.uint8)
        pixels[31:48, 43:66] = patch
        # This fixture really has several threshold crossings around one object.
        raw = cv2.matchTemplate(cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY), gray,
                                cv2.TM_CCOEFF_NORMED)
        self.assertGreater(np.count_nonzero(raw >= 0.93), 1)
        result = self.run_scene(pixels, templates=[{
            "id": "target", "path": "smooth.png", "threshold": 0.93,
        }])
        hits = self.template_hits(result)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["bbox"], [43, 31, 23, 17])
        self.assertFalse(hits[0]["ambiguous"])
        self.assertEqual(result["state"]["label"], "ready")

    def test_blank_noise_and_occlusion_do_not_create_positive_state(self):
        covered = self.scene()
        covered[25:38, 30:47] = self.patch
        covered[25:38, 30:40] = 0
        samples = {"blank": np.zeros((80, 100, 3), dtype=np.uint8),
                   "noise": self.scene(), "occluded": covered}
        for name, pixels in samples.items():
            with self.subTest(sample=name):
                result = self.run_scene(pixels)
                self.assertEqual(self.template_hits(result), [])
                self.assertEqual(result["state"]["label"], "unknown")
                self.assertEqual(result["state"]["evidence_ids"], [])

    def test_constant_templates_are_rejected_instead_of_matching_everywhere(self):
        image = self.write_image("scene.png", self.scene())
        for level in (0, 127, 255):
            with self.subTest(level=level):
                self.write_image("constant.png", np.full((10, 12, 3), level, np.uint8))
                config = self.config(templates=[{
                    "id": "target", "path": "constant.png", "threshold": 0.9,
                }])
                with self.assertRaises(ValueError):
                    observe(image, config)

    def test_wrong_dimensions_bad_image_and_missing_files_fail_explicitly(self):
        image = self.write_image("scene.png", self.scene())
        config = self.config()
        corrupt = self.root / "bad.png"
        corrupt.write_bytes(b"This is deliberately not an image.")
        empty = self.root / "empty.png"
        empty.write_bytes(b"")
        with self.subTest(case="dimensions"), self.assertRaises(ValueError):
            observe(image, self.config(expected_size=[99, 80]))
        with self.subTest(case="corrupt"), self.assertRaises(ValueError):
            observe(corrupt, config)
        with self.subTest(case="zero_bytes"), self.assertRaises(ValueError):
            observe(empty, config)
        with self.subTest(case="missing_image"), self.assertRaises(FileNotFoundError):
            observe(self.root / "missing.png", config)
        with self.subTest(case="missing_config"), self.assertRaises(FileNotFoundError):
            observe(image, self.root / "missing.json")
        with self.subTest(case="missing_template"), self.assertRaises(FileNotFoundError):
            observe(image, self.config(templates=[{
                "id": "target", "path": "missing-template.png", "threshold": 0.99,
            }]))

    def test_invalid_or_too_small_regions_are_rejected(self):
        image = self.write_image("scene.png", self.scene())
        invalid = [[-1, 0, 40, 40], [0, 0, 101, 80], [0, 0, 0, 20],
                   [0.5, 0, 40, 40], [True, 0, 40, 40], [0, 0, 16, 12]]
        for roi in invalid:
            with self.subTest(roi=roi), self.assertRaises(ValueError):
                observe(image, self.config(templates=[{
                    "id": "target", "path": "target.png", "roi": roi,
                }]))
        with self.subTest(case="out_of_bounds_mask"), self.assertRaises(ValueError):
            observe(image, self.config(masks=[[90, 70, 11, 11]]))

    def test_mask_is_applied_before_ocr_and_sensitive_elements_are_removed(self):
        pixels = self.scene()
        pixels[2:15, 2:19] = self.patch
        image = self.write_image("private.png", pixels)
        original_file = image.read_bytes()
        masks = [[2, 2, 17, 13]]
        calls = []

        def fake_ocr(actual, minimum_score):
            calls.append(minimum_score)
            self.assertTrue(np.all(actual[2:15, 2:19] == 0))
            np.testing.assert_array_equal(actual[30:40, 30:50], pixels[30:40, 30:50])
            return [{"kind": "text", "label": label, "source": "fake_ocr",
                     "score": 0.98, "bbox": box, "center": [box[0], box[1]]}
                    for label, box in [("secret", [2, 2, 10, 8]),
                                       ("partial-secret", [17, 12, 10, 10]),
                                       ("公开提示", [30, 30, 20, 10])]]

        config = self.config(masks=masks, ocr_min_score=0.74,
                             states=[{"name": "public", "all_text": ["公开提示"]}])
        result = observe(image, config, ocr=True, ocr_reader=fake_ocr)
        self.assertEqual(calls, [0.74])
        self.assertEqual([item["label"] for item in result["elements"]], ["公开提示"])
        self.assertEqual(result["state"]["label"], "public")
        self.assertEqual(result["state"]["evidence_ids"], [result["elements"][0]["id"]])
        expected = pixels.copy()
        expected[2:15, 2:19] = 0
        self.assertEqual(result["image"]["sha256"], hashlib.sha256(expected.tobytes()).hexdigest())
        self.assertEqual(image.read_bytes(), original_file, "Observation must not rewrite its input")
        # Changing only the secret area must not leak through the published digest.
        pixels[2:15, 2:19] = 255
        other = self.write_image("different-secret.png", pixels)
        self.assertEqual(observe(other, config)["image"]["sha256"], result["image"]["sha256"])

    def test_conflicting_scene_rules_remain_unknown(self):
        pixels = self.scene()
        pixels[15:28, 35:52] = self.patch
        result = self.run_scene(pixels, states=[
            {"name": "login", "requires": ["target"]},
            {"name": "character_selection", "requires": ["target"]},
        ])
        self.assertEqual(len(self.template_hits(result)), 1)
        self.assertEqual(result["state"]["label"], "unknown")
        self.assertEqual(result["state"]["evidence_ids"], [])
        self.assertTrue(any("ambiguous_scene" in warning for warning in result["warnings"]))

    def test_ocr_phrase_cannot_be_invented_by_joining_distant_text_boxes(self):
        image = self.write_image("ocr-scene.png", self.scene())
        config = self.config(templates=[], states=[{
            "name": "logged_in", "all_text": ["登录成功"],
        }])

        def texts(items):
            return [{"kind": "text", "label": label, "source": "fake_ocr",
                     "score": 0.98, "bbox": box, "center": [box[0], box[1]]}
                    for label, box in items]

        with self.subTest(case="distant_boxes_are_not_a_phrase"):
            result = observe(image, config, ocr=True, ocr_reader=lambda *_: texts([
                ("登录", [1, 1, 20, 10]), ("成功", [75, 65, 20, 10]),
            ]))
            self.assertEqual(len(result["elements"]), 2)
            self.assertEqual(result["state"]["label"], "unknown")
            self.assertEqual(result["state"]["evidence_ids"], [])

        with self.subTest(case="one_box_has_the_phrase"):
            result = observe(image, config, ocr=True, ocr_reader=lambda *_: texts([
                ("登录成功", [20, 25, 50, 12]),
            ]))
            self.assertEqual(result["state"]["label"], "logged_in")
            self.assertEqual(result["state"]["evidence_ids"], [result["elements"][0]["id"]])

    def assert_cli_error(self, *args):
        process = subprocess.run(
            [sys.executable, "-B", "-m", "microvision", *map(str, args)],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, encoding="utf-8", errors="replace", timeout=20,
        )
        self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
        self.assertNotIn("Traceback", process.stdout + process.stderr)
        payload = json.loads(process.stdout)
        self.assertEqual(payload["mode"], "observation_only")
        self.assertEqual(payload["state"]["label"], "unknown")
        self.assertEqual(payload["state"]["evidence_ids"], [])
        self.assertEqual(payload["elements"], [])
        self.assertTrue(payload.get("error"))

    def test_cli_bad_and_empty_images_produce_json_errors_without_tracebacks(self):
        for name, content in [("corrupt.png", b"invalid-image"), ("zero.png", b"")]:
            with self.subTest(file=name):
                path = self.root / name
                path.write_bytes(content)
                self.assert_cli_error(path)

    def test_cli_output_directory_conflict_produces_json_error(self):
        image = self.write_image("valid.png", self.scene())
        self.assert_cli_error(image, "--output", self.root)

    def test_calibration_requires_true_flag_and_declared_dimensions(self):
        pixels = self.scene()
        pixels[15:28, 35:52] = self.patch
        image = self.write_image("scene.png", pixels)
        config = self.config()
        baseline = json.loads(config.read_text(encoding="utf-8"))
        for case, flag in [("missing_flag", None), ("false_flag", False),
                           ("text_flag", "true"), ("integer_flag", 1),
                           ("missing_size", True)]:
            with self.subTest(case=case):
                value = dict(baseline)
                if case == "missing_flag":
                    del value["calibrated"]
                else:
                    value["calibrated"] = flag
                if case == "missing_size":
                    del value["expected_size"]
                config.write_text(json.dumps(value), encoding="utf-8")
                result = observe(image, config)
                self.assertEqual(len(self.template_hits(result)), 1)
                self.assertEqual(result["state"]["label"], "unknown")
                self.assertTrue(any("uncalibrated" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
