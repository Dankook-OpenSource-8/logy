import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.ai_video_verification import (
    FRAME_TIMESTAMPS,
    OCR_MAX_DIMENSION,
    prepare_ocr_image,
    select_best_verification_frame,
)
from core.study_image_classifier import StudyClassifierResult


class AiVideoVerificationTest(unittest.TestCase):
    def test_video_verification_uses_two_representative_frames(self):
        self.assertEqual(FRAME_TIMESTAMPS, (1.5, 3.5))

    def test_prepare_ocr_image_resizes_large_frame(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "large.jpg"
            Image.new("RGB", (2400, 1200), color="white").save(frame_path)

            ocr_path = prepare_ocr_image(frame_path)

            with Image.open(ocr_path) as image:
                width, height = image.size

        self.assertNotEqual(ocr_path, frame_path)
        self.assertLessEqual(max(width, height), OCR_MAX_DIMENSION)

    def test_missing_fine_tuned_classifier_does_not_pollute_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frame.jpg"
            frame_path.write_bytes(b"fake")

            with (
                patch("core.ai_video_verification.score_frame_quality", return_value=10),
                patch("core.ai_video_verification.score_scene_context", return_value=(25, 0, "study=0.55")),
                patch("core.ai_video_verification.extract_text", return_value=""),
                patch("core.ai_video_verification.score_subject_similarity", return_value=(10, "OCR 텍스트가 없습니다.")),
                patch(
                    "core.ai_video_verification.score_with_study_classifier",
                    return_value=StudyClassifierResult(
                        available=False,
                        study_probability=None,
                        scene_score=0,
                        forbidden_penalty=0,
                        reason="fine_tuned_classifier=not_ready",
                    ),
                ),
            ):
                result = select_best_verification_frame([frame_path], "수학")

        self.assertEqual(result.classifier_reason, "")
        self.assertEqual(result.total_score, 35)

    def test_fine_tuned_classifier_replaces_scene_prompt_score(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frame.jpg"
            frame_path.write_bytes(b"fake")

            with (
                patch("core.ai_video_verification.score_frame_quality", return_value=10),
                patch("core.ai_video_verification.score_scene_context") as scene_context,
                patch("core.ai_video_verification.extract_text", return_value=""),
                patch("core.ai_video_verification.score_subject_similarity", return_value=(10, "OCR 텍스트가 없습니다.")),
                patch(
                    "core.ai_video_verification.score_with_study_classifier",
                    return_value=StudyClassifierResult(
                        available=True,
                        study_probability=0.9,
                        scene_score=40,
                        forbidden_penalty=0,
                        reason="fine_tuned_study_probability=0.90",
                    ),
                ),
            ):
                result = select_best_verification_frame([frame_path], "수학")

        scene_context.assert_not_called()
        self.assertEqual(result.scene_score, 40)
        self.assertEqual(result.forbidden_penalty, 0)
        self.assertEqual(result.classifier_reason, "fine_tuned_study_probability=0.90")
        self.assertEqual(result.total_score, 50)

    def test_total_score_uses_scene_and_subject_without_forbidden_penalty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frame.jpg"
            frame_path.write_bytes(b"fake")

            with (
                patch("core.ai_video_verification.score_frame_quality", return_value=10),
                patch("core.ai_video_verification.score_scene_context", return_value=(20, 30, "study=0.45")),
                patch("core.ai_video_verification.extract_text", return_value="open source"),
                patch("core.ai_video_verification.score_subject_similarity", return_value=(30, "subject evidence")),
                patch(
                    "core.ai_video_verification.score_with_study_classifier",
                    return_value=StudyClassifierResult(
                        available=False,
                        study_probability=None,
                        scene_score=0,
                        forbidden_penalty=0,
                        reason="fine_tuned_classifier=not_ready",
                    ),
                ),
            ):
                result = select_best_verification_frame([frame_path], "오픈소스")

        self.assertEqual(result.forbidden_penalty, 30)
        self.assertEqual(result.total_score, 72)


if __name__ == "__main__":
    unittest.main()
