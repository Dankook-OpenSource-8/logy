from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from core.ai_video_verification import (
    FRAME_TIMESTAMPS,
    OCR_MAX_DIMENSION,
    FrameVerificationResult,
    VerificationResult,
    extract_text,
    has_ocr_timeout,
    prepare_ocr_image,
    select_best_verification_frame,
    score_subject_similarity,
    verify_study_video,
)
from api.routes import _should_allow_auth_retake, _verification_result_response
from core.study_image_classifier import StudyClassifierResult


class AiVideoVerificationTest(unittest.TestCase):
    def test_video_verification_uses_single_midpoint_frame(self):
        self.assertEqual(FRAME_TIMESTAMPS, (2.0,))

    def test_prepare_ocr_image_resizes_large_frame(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "large.jpg"
            Image.new("RGB", (2400, 1200), color="white").save(frame_path)

            ocr_path = prepare_ocr_image(frame_path)

            with Image.open(ocr_path) as image:
                width, height = image.size

        self.assertNotEqual(ocr_path, frame_path)
        self.assertLessEqual(max(width, height), OCR_MAX_DIMENSION)

    def test_extract_text_uses_external_ocr_server_when_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frame.jpg"
            Image.new("RGB", (320, 240), color="white").save(frame_path)

            class FakeResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"text": "데이터베이스 메모리 주소"}

            with (
                patch.dict("os.environ", {"OCR_SERVER_URL": "https://ocr.test"}, clear=False),
                patch("httpx.post", return_value=FakeResponse()) as post,
                patch("core.ai_video_verification.read_ocr_text_with_timeout") as local_ocr,
            ):
                text = extract_text(frame_path)

        self.assertEqual(text, "데이터베이스 메모리 주소")
        post.assert_called_once()
        local_ocr.assert_not_called()

    def test_missing_fine_tuned_classifier_does_not_pollute_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frame.jpg"
            frame_path.write_bytes(b"fake")

            with (
                patch("core.ai_video_verification.score_frame_quality", return_value=10),
                patch("core.ai_video_verification.score_scene_context", return_value=(25, 0, "study=0.55")),
                patch("core.ai_video_verification.extract_text", return_value=""),
                patch("core.ai_video_verification.score_subject_similarity", return_value=(0, "OCR 텍스트가 없습니다.")),
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
        self.assertEqual(result.total_score, 25)

    def test_fine_tuned_classifier_replaces_scene_prompt_score(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frame.jpg"
            frame_path.write_bytes(b"fake")

            with (
                patch("core.ai_video_verification.score_frame_quality", return_value=10),
                patch("core.ai_video_verification.score_scene_context") as scene_context,
                patch("core.ai_video_verification.extract_text", return_value=""),
                patch("core.ai_video_verification.score_subject_similarity", return_value=(0, "OCR 텍스트가 없습니다.")),
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
        self.assertEqual(result.total_score, 40)

    def test_total_score_uses_scene_and_subject_without_forbidden_penalty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frame.jpg"
            frame_path.write_bytes(b"fake")

            with (
                patch("core.ai_video_verification.score_frame_quality", return_value=10),
                patch("core.ai_video_verification.score_scene_context", return_value=(20, 30, "study=0.45")),
                patch("core.ai_video_verification.extract_text", return_value="open source"),
                patch("core.ai_video_verification.score_subject_similarity", return_value=(40, "subject evidence")),
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

    def test_first_passing_frame_stops_scoring(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_frame = Path(temp_dir) / "frame_2_0.jpg"
            second_frame = Path(temp_dir) / "frame_extra.jpg"
            first_frame.write_bytes(b"fake-1")
            second_frame.write_bytes(b"fake-2")

            with (
                patch("core.ai_video_verification.score_frame_quality", return_value=10),
                patch("core.ai_video_verification.extract_text", return_value="computer architecture memory") as extract_text,
                patch("core.ai_video_verification.score_subject_similarity", return_value=(40, "subject evidence")),
                patch(
                    "core.ai_video_verification.score_with_study_classifier",
                    return_value=StudyClassifierResult(
                        available=True,
                        study_probability=0.9,
                        scene_score=35,
                        forbidden_penalty=0,
                        reason="fine_tuned_study_probability=0.90",
                    ),
                ),
            ):
                result = select_best_verification_frame([first_frame, second_frame], "컴퓨터구조")

        self.assertEqual(result.frame_path, first_frame)
        self.assertEqual(result.total_score, 75)
        extract_text.assert_called_once_with(first_frame)

    def test_ocr_timeout_reason_is_detected_for_retake(self):
        self.assertTrue(
            has_ocr_timeout("OCR 텍스트가 없어 과목 관련성 점수를 부여하지 않았습니다. (OCRTimeout: OCR 처리 시간이 40초를 초과했습니다.)")
        )
        self.assertFalse(has_ocr_timeout("OCR 텍스트가 없습니다."))

    def test_subject_text_score_rewards_direct_subject_match(self):
        with patch("core.ai_video_verification.calculate_text_similarity", return_value=0.35):
            score, reason = score_subject_similarity(
                "데이터베이스",
                "데이터베이스 설계와 DBMS 트랜잭션 정규화 릴레이션을 공부했습니다.",
            )

        self.assertEqual(score, 40)
        self.assertIn("subject_direct_match", reason)

    def test_subject_text_score_limits_related_but_wrong_subject(self):
        with patch("core.ai_video_verification.calculate_text_similarity", return_value=0.72):
            score, reason = score_subject_similarity(
                "데이터베이스",
                "CPU 캐시 메모리 계층 레지스터 파이프라인 명령어 실행 과정을 정리했습니다.",
            )

        self.assertLessEqual(score, 20)
        self.assertIn("subject_cap=20", reason)

    def test_subject_text_score_gives_middle_score_for_one_core_keyword(self):
        with patch("core.ai_video_verification.calculate_text_similarity", return_value=0.25):
            score, reason = score_subject_similarity(
                "컴퓨터구조",
                "오늘은 CPU 동작 흐름을 간단히 복습했습니다.",
            )

        self.assertGreaterEqual(score, 24)
        self.assertLessEqual(score, 30)
        self.assertIn("subject_keyword_matches=1", reason)

    def test_java_programming_uses_oop_keywords_for_subject_match(self):
        with patch("core.ai_video_verification.calculate_text_similarity", return_value=0.18):
            score, reason = score_subject_similarity(
                "자바 프로그래밍",
                "Calculator 클래스에서 interface를 구현하고 상속 관계의 메서드 오버라이드를 확인했습니다.",
            )

        self.assertGreaterEqual(score, 36)
        self.assertIn("subject_keyword_matches", reason)

    def test_discrete_math_uses_logic_and_set_keywords(self):
        with patch("core.ai_video_verification.calculate_text_similarity", return_value=0.16):
            score, reason = score_subject_similarity(
                "이산수학",
                "명제 논리와 집합 관계 그래프 귀납법 문제를 정리했습니다.",
            )

        self.assertGreaterEqual(score, 36)
        self.assertIn("subject_keyword_matches", reason)

    def test_formula_heavy_subject_rewards_math_notation(self):
        with patch("core.ai_video_verification.calculate_text_similarity", return_value=0.14):
            score, reason = score_subject_similarity(
                "미적분",
                "lim x->0 f(x), x^2 + 3x, integral dx, sin theta 공식을 풀었습니다.",
            )

        self.assertGreaterEqual(score, 32)
        self.assertIn("math_formula_evidence", reason)

    def test_video_verification_approves_from_65_points(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frame.jpg"
            frame_path.write_bytes(b"fake")
            frame_result = FrameVerificationResult(
                frame_path=frame_path,
                total_score=65,
                scene_score=35,
                text_score=30,
                quality_score=10,
                forbidden_penalty=0,
                scene_reason="scene",
                text_reason="text",
                classifier_reason="classifier",
            )

            with (
                patch("core.ai_video_verification.download_video"),
                patch("core.ai_video_verification.extract_candidate_frames", return_value=[frame_path]),
                patch("core.ai_video_verification.select_best_verification_frame", return_value=frame_result),
                patch("core.ai_video_verification.time.monotonic", side_effect=[0, 20]),
            ):
                result = verify_study_video("https://storage.test/video.mp4", "데이터베이스")

        self.assertTrue(result.approved)
        self.assertEqual(result.status, "성공")

    def test_video_verification_requests_retake_after_total_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frame.jpg"
            frame_path.write_bytes(b"fake")
            frame_result = FrameVerificationResult(
                frame_path=frame_path,
                total_score=90,
                scene_score=55,
                text_score=35,
                quality_score=10,
                forbidden_penalty=0,
                scene_reason="scene",
                text_reason="text",
                classifier_reason="classifier",
            )

            with (
                patch("core.ai_video_verification.download_video"),
                patch("core.ai_video_verification.extract_candidate_frames", return_value=[frame_path]),
                patch("core.ai_video_verification.select_best_verification_frame", return_value=frame_result),
                patch("core.ai_video_verification.time.monotonic", side_effect=[0, 61]),
            ):
                result = verify_study_video("https://storage.test/video.mp4", "데이터베이스")

        self.assertFalse(result.approved)
        self.assertEqual(result.status, "실패")
        self.assertIn("재인증", result.reason)

    def test_retake_result_keeps_auth_window_open(self):
        result = VerificationResult(
            approved=False,
            status="실패",
            total_score=58,
            reason="학습 여부가 애매하여 재촬영이 필요합니다.",
            scene_score=35,
            text_score=13,
            quality_score=10,
            forbidden_penalty=0,
            representative_frame_path=None,
        )

        self.assertTrue(_should_allow_auth_retake(result))

    def test_low_score_failure_does_not_allow_retake_window(self):
        result = VerificationResult(
            approved=False,
            status="실패",
            total_score=30,
            reason="학습 장면 또는 과목 관련성이 부족합니다.",
            scene_score=20,
            text_score=0,
            quality_score=10,
            forbidden_penalty=0,
            representative_frame_path=None,
        )

        self.assertFalse(_should_allow_auth_retake(result))

    def test_verification_result_response_includes_retake_expiration(self):
        next_auth_time = datetime(2026, 6, 9, 13, 40, tzinfo=timezone.utc)
        auth_log = SimpleNamespace(
            id=1,
            study_session_id=2,
            status="실패",
            video_url="https://storage.test/video.mp4",
            verification_score=56,
            verification_reason="학습 여부가 애매하여 재촬영이 필요합니다.",
            scene_score=40,
            text_score=16,
            quality_score=14,
            forbidden_penalty=0,
            representative_frame_path=None,
            created_at=next_auth_time - timedelta(seconds=30),
            verified_at=next_auth_time,
            session=SimpleNamespace(next_auth_time=next_auth_time),
        )

        response = _verification_result_response(auth_log)

        self.assertEqual(
            response.auth_expires_at,
            next_auth_time + timedelta(seconds=60),
        )


if __name__ == "__main__":
    unittest.main()
