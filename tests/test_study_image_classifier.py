import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.study_image_classifier import (
    get_classifier_components,
    score_probability,
    score_with_study_classifier,
)


class StudyImageClassifierTest(unittest.TestCase):
    def test_score_probability_converts_study_probability_to_scene_score(self):
        scene_score, forbidden_penalty = score_probability(0.8)

        self.assertEqual(scene_score, 36)
        self.assertEqual(forbidden_penalty, 0)

    def test_score_probability_clamps_probability_range(self):
        high_scene_score, high_penalty = score_probability(1.5)
        low_scene_score, low_penalty = score_probability(-0.5)

        self.assertEqual((high_scene_score, high_penalty), (45, 0))
        self.assertEqual((low_scene_score, low_penalty), (0, 0))

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

    def test_classifier_allows_remote_model_download_by_default(self):
        checkpoint = {
            "input_dim": 2,
            "clip_model_name": "openai/clip-vit-base-patch32",
            "classifier_state_dict": {
                "weight": Mock(),
                "bias": Mock(),
            },
        }
        get_classifier_components.cache_clear()
        with (
            patch("core.study_image_classifier.MODEL_PATH", Path("models/study_classifier.pt")),
            patch("torch.load", return_value=checkpoint),
            patch("torch.nn.Linear") as linear,
            patch("transformers.CLIPModel.from_pretrained") as clip_from_pretrained,
            patch("transformers.CLIPProcessor.from_pretrained") as processor_from_pretrained,
        ):
            linear.return_value.load_state_dict.return_value = None
            linear.return_value.eval.return_value = None
            clip_from_pretrained.return_value.eval.return_value = None

            get_classifier_components()

        clip_from_pretrained.assert_called_once_with(
            "openai/clip-vit-base-patch32",
            local_files_only=False,
        )
        processor_from_pretrained.assert_called_once_with(
            "openai/clip-vit-base-patch32",
            local_files_only=False,
        )
        get_classifier_components.cache_clear()


if __name__ == "__main__":
    unittest.main()
