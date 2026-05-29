import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.study_image_classifier import score_probability, score_with_study_classifier


class StudyImageClassifierTest(unittest.TestCase):
    def test_score_probability_converts_study_probability_to_scene_score(self):
        scene_score, forbidden_penalty = score_probability(0.8)

        self.assertEqual(scene_score, 36)
        self.assertEqual(forbidden_penalty, 8)

    def test_score_probability_clamps_probability_range(self):
        high_scene_score, high_penalty = score_probability(1.5)
        low_scene_score, low_penalty = score_probability(-0.5)

        self.assertEqual((high_scene_score, high_penalty), (45, 0))
        self.assertEqual((low_scene_score, low_penalty), (0, 40))

    def test_missing_model_returns_unavailable_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.pt"
            with patch("core.study_image_classifier.MODEL_PATH", missing_path):
                result = score_with_study_classifier(Path("frame.jpg"))

        self.assertFalse(result.available)
        self.assertIsNone(result.study_probability)
        self.assertEqual(result.scene_score, 0)
        self.assertEqual(result.forbidden_penalty, 0)
        self.assertEqual(result.reason, "fine_tuned_classifier=not_ready")


if __name__ == "__main__":
    unittest.main()
