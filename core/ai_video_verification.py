import shutil
import subprocess
import tempfile
import urllib.request
import uuid
import os
from dataclasses import dataclass
from pathlib import Path

from core.study_image_classifier import score_with_study_classifier


FRAME_TIMESTAMPS = (1.5, 3.5)
OCR_MAX_DIMENSION = 1120
APPROVAL_THRESHOLD = 70
RETAKE_THRESHOLD = 50
SCENE_SCORE_MAX = 60
TEXT_SCORE_MAX = 40
DEFAULT_TEXT_SCORE = 0
STRONG_TEXT_SCORE = 36

STUDY_PROMPTS = (
    "a person studying with books and notes",
    "a person studying on a laptop",
    "a person studying on a tablet",
    "a laptop screen showing handwritten study notes",
    "a digital notebook with math equations and diagrams",
    "a person reading a textbook",
    "a person solving problems on paper",
    "a person solving math equations",
    "a desk with study materials and handwritten notes",
    "an online lecture or educational document on a screen",
    "a code editor or programming lecture used for studying",
    "a laptop screen showing charts, graphs, or analytical data for studying",
    "a person studying finance, economics, or market analysis on a laptop",
    "educational charts and graphs on a computer screen",
)

FORBIDDEN_PROMPTS = (
    "a person playing a video game",
    "a social media feed on a phone or computer",
    "an entertainment video or movie on a screen",
    "an online shopping website",
    "a chat messenger conversation",
    "a music video or streaming platform for entertainment",
    "a stock trading app used for buying and selling stocks",
)

SUBJECT_ALIASES = {
    # OCR은 한국어 과목명보다 화면 속 영문 약어를 더 잘 잡는 경우가 많아 보조 키워드만 가볍게 붙입니다.
    "컴퓨터구조": "computer architecture cpu cache memory pipeline branch instruction datapath register alu if id ex mem store load hazard control",
    "자료구조": "data structure hash bucket collision graph tree stack queue heap dfs bfs connected component",
    "알고리즘": "algorithm dynamic programming greedy graph shortest path minimum spanning tree prim kruskal connected component",
    "데이터베이스": "database sql erd entity relation table customer primary key foreign key query ddl dml schema",
    "선형대수": "linear algebra vector matrix scalar basis span transformation eigenvalue determinant multiplication",
    "운영체제": "operating system process thread scheduler scheduling deadlock semaphore mutex memory paging virtual memory kernel file system",
    "컴퓨터네트워크": "computer network tcp ip udp http dns packet routing router switch subnet osi congestion socket",
    "네트워크": "network tcp ip udp http dns packet routing router switch subnet osi congestion socket",
    "소프트웨어공학": "software engineering requirement design pattern uml use case testing agile scrum architecture refactoring",
    "웹프로그래밍": "web programming html css javascript typescript react node api request response dom component state",
    "프로그래밍": "programming code function variable class object loop array list python java c javascript typescript",
    "인공지능": "artificial intelligence machine learning deep learning neural network model training inference classification regression",
    "머신러닝": "machine learning dataset feature label train validation test accuracy loss classifier regression clustering",
    "통계": "statistics probability distribution mean variance standard deviation hypothesis p value regression correlation sample",
    "확률": "probability random variable distribution expectation variance bayes conditional probability sample event",
    "회계": "accounting asset liability equity revenue expense debit credit balance sheet income statement journal",
    "경제": "economics demand supply elasticity market price cost revenue monopoly inflation gdp interest rate",
    "경영": "management strategy organization operation finance marketing leadership swot kpi performance decision",
    "마케팅": "marketing segmentation targeting positioning brand customer promotion price product place campaign conversion",
    "재무관리": "finance present value future value cash flow interest rate npv irr portfolio risk return",
    "물리": "physics force energy momentum velocity acceleration wave electric magnetic quantum equation",
    "화학": "chemistry molecule atom reaction bond acid base equilibrium concentration molar electron",
    "생명과학": "biology cell dna rna protein enzyme gene chromosome metabolism organism evolution",
    "전자회로": "electronic circuit voltage current resistance capacitor transistor diode op amp frequency signal",
    "디지털논리": "digital logic boolean gate flip flop latch mux decoder encoder truth table karnaugh",
}

ACADEMIC_TEXT_HINTS = {
    "algorithm",
    "architecture",
    "asset",
    "alu",
    "api",
    "atom",
    "bayes",
    "biology",
    "bond",
    "brand",
    "branch",
    "boolean",
    "cache",
    "campaign",
    "capacitor",
    "cash",
    "cell",
    "chart",
    "chapter",
    "chemistry",
    "chromosome",
    "class",
    "collision",
    "component",
    "concentration",
    "congestion",
    "control",
    "correlation",
    "cost",
    "cpu",
    "credit",
    "css",
    "customer",
    "database",
    "datapath",
    "deadlock",
    "debit",
    "decoder",
    "deep",
    "demand",
    "determinant",
    "diode",
    "distribution",
    "dna",
    "dns",
    "dom",
    "dfs",
    "dml",
    "ddl",
    "erd",
    "elasticity",
    "electric",
    "electron",
    "encoder",
    "energy",
    "enzyme",
    "equation",
    "equilibrium",
    "entity",
    "equity",
    "expectation",
    "expense",
    "execution",
    "feature",
    "finance",
    "flow",
    "force",
    "foreign",
    "frequency",
    "function",
    "gate",
    "gdp",
    "gene",
    "greedy",
    "graph",
    "hash",
    "heap",
    "html",
    "http",
    "hypothesis",
    "income",
    "inflation",
    "inference",
    "instruction",
    "interest",
    "java",
    "javascript",
    "journal",
    "kernel",
    "key",
    "label",
    "latch",
    "lecture",
    "liability",
    "logic",
    "loss",
    "linear",
    "load",
    "magnetic",
    "market",
    "marketing",
    "matrix",
    "mean",
    "memory",
    "mem",
    "model",
    "molecule",
    "momentum",
    "monopoly",
    "mutex",
    "multiplication",
    "neural",
    "network",
    "npv",
    "object",
    "organism",
    "packet",
    "paging",
    "portfolio",
    "probability",
    "process",
    "pipeline",
    "processor",
    "protein",
    "python",
    "quantum",
    "query",
    "random",
    "react",
    "regression",
    "relation",
    "register",
    "requirement",
    "resistance",
    "return",
    "revenue",
    "risk",
    "rna",
    "router",
    "routing",
    "sample",
    "scalar",
    "scheduler",
    "scrum",
    "segmentation",
    "semaphore",
    "schema",
    "signal",
    "socket",
    "software",
    "sql",
    "stack",
    "state",
    "statistics",
    "store",
    "strategy",
    "subnet",
    "supply",
    "switch",
    "table",
    "tcp",
    "testing",
    "theorem",
    "thread",
    "training",
    "transformation",
    "transistor",
    "typescript",
    "udp",
    "uml",
    "variance",
    "vector",
    "velocity",
    "voltage",
    "volume",
    "wave",
    "회계",
    "자산",
    "부채",
    "자본",
    "수익",
    "비용",
    "경제",
    "수요",
    "공급",
    "탄력성",
    "확률",
    "통계",
    "분산",
    "표준편차",
    "가설",
    "회귀",
    "상관",
    "운영체제",
    "프로세스",
    "스레드",
    "스케줄링",
    "교착",
    "페이징",
    "네트워크",
    "패킷",
    "라우팅",
    "소켓",
    "인공지능",
    "머신러닝",
    "학습",
    "분류",
    "회로",
    "전압",
    "전류",
    "저항",
    "트랜지스터",
    "물리",
    "힘",
    "에너지",
    "운동량",
    "화학",
    "분자",
    "원자",
    "반응",
    "생명",
    "세포",
    "유전자",
    "market",
    "price",
    "stock",
    "trading",
    "graph",
    "제어",
    "구조",
    "곱셈",
    "대수",
    "명령",
    "메모리",
    "벡터",
    "선형",
    "신호",
    "스칼라",
    "연산",
    "행렬",
    "자료",
    "거래",
    "시장",
    "주가",
    "주식",
    "차트",
    "챕터",
}


@dataclass
class VerificationResult:
    approved: bool
    status: str
    total_score: int
    reason: str
    scene_score: int
    text_score: int
    quality_score: int
    forbidden_penalty: int
    representative_frame_path: str | None


@dataclass
class FrameVerificationResult:
    frame_path: Path
    total_score: int
    scene_score: int
    text_score: int
    quality_score: int
    forbidden_penalty: int
    scene_reason: str
    text_reason: str
    classifier_reason: str


_clip_model = None
_clip_processor = None
_clip_torch = None
_clip_error = None
_ocr_reader = None
_ocr_error = None
_embedding_model = None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _short_error(error: Exception) -> str:
    message = str(error).strip()
    if len(message) > 160:
        message = f"{message[:157]}..."
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def verify_study_video(video_url: str, subject: str | None) -> VerificationResult:
    with tempfile.TemporaryDirectory(prefix="logy_verify_") as temp_dir:
        work_dir = Path(temp_dir)
        video_path = work_dir / "source_video"
        download_video(video_url, video_path)

        frame_paths = extract_candidate_frames(video_path, work_dir)
        if not frame_paths:
            return VerificationResult(
                approved=False,
                status="실패",
                total_score=0,
                reason="대표 프레임을 추출하지 못했습니다.",
                scene_score=0,
                text_score=0,
                quality_score=0,
                forbidden_penalty=0,
                representative_frame_path=None,
            )

        frame_result = select_best_verification_frame(frame_paths, subject)
        representative_frame = frame_result.frame_path
        quality_score = frame_result.quality_score
        scene_score = frame_result.scene_score
        forbidden_penalty = frame_result.forbidden_penalty
        scene_reason = frame_result.scene_reason
        text_score = frame_result.text_score
        text_reason = frame_result.text_reason
        classifier_reason = frame_result.classifier_reason
        total_score = frame_result.total_score

        approved = total_score >= APPROVAL_THRESHOLD
        if total_score >= APPROVAL_THRESHOLD:
            reason = "학습 장면 맥락과 과목 관련성이 충분합니다."
        elif total_score >= RETAKE_THRESHOLD:
            reason = "학습 여부가 애매하여 재촬영이 필요합니다."
        else:
            reason = "학습 장면 또는 과목 관련성이 부족합니다."

        details = "; ".join(
            detail for detail in (scene_reason, classifier_reason, text_reason) if detail
        )
        if details:
            reason = f"{reason} ({details})"

        return VerificationResult(
            approved=approved,
            status="성공" if approved else "실패",
            total_score=total_score,
            reason=reason,
            scene_score=scene_score,
            text_score=text_score,
            quality_score=quality_score,
            forbidden_penalty=forbidden_penalty,
            representative_frame_path=save_representative_frame(representative_frame),
        )


def download_video(video_url: str, destination: Path) -> None:
    request = urllib.request.Request(
        video_url,
        headers={"User-Agent": "LogyVideoVerifier/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        destination.write_bytes(response.read())


def extract_candidate_frames(video_path: Path, work_dir: Path) -> list[Path]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg가 설치되어 있지 않습니다.")

    frame_paths: list[Path] = []
    for timestamp in FRAME_TIMESTAMPS:
        output_path = work_dir / f"frame_{str(timestamp).replace('.', '_')}.jpg"
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if output_path.exists() and output_path.stat().st_size > 0:
            frame_paths.append(output_path)

    return frame_paths


def select_representative_frame(frame_paths: list[Path]) -> tuple[Path, int]:
    scored_frames = [(frame_path, score_frame_quality(frame_path)) for frame_path in frame_paths]
    scored_frames.sort(key=lambda item: item[1], reverse=True)
    return scored_frames[0]


def select_best_verification_frame(
    frame_paths: list[Path],
    subject: str | None,
) -> FrameVerificationResult:
    results: list[FrameVerificationResult] = []
    for frame_path in frame_paths:
        quality_score = score_frame_quality(frame_path)
        classifier_result = score_with_study_classifier(frame_path)
        if classifier_result.available:
            scene_score = classifier_result.scene_score
            forbidden_penalty = 0
            scene_reason = ""
            classifier_reason = classifier_result.reason
        else:
            scene_score, forbidden_penalty, scene_reason = score_scene_context(frame_path, subject)
            classifier_reason = (
                classifier_result.reason
                if classifier_result.reason != "fine_tuned_classifier=not_ready"
                else ""
            )

        extracted_text = extract_text(frame_path)
        text_score, text_reason = score_subject_similarity(subject, extracted_text)
        total_score = max(
            0,
            min(100, scene_score + text_score),
        )
        if has_strong_study_evidence(text_score):
            total_score = max(total_score, 72)

        results.append(
            FrameVerificationResult(
                frame_path=frame_path,
                total_score=total_score,
                scene_score=scene_score,
                text_score=text_score,
                quality_score=quality_score,
                forbidden_penalty=forbidden_penalty,
                scene_reason=scene_reason,
                text_reason=text_reason,
                classifier_reason=classifier_reason,
            )
        )

    results.sort(key=lambda result: (result.total_score, result.quality_score), reverse=True)
    return results[0]


def score_frame_quality(frame_path: Path) -> int:
    try:
        import cv2

        image = cv2.imread(str(frame_path))
        if image is None:
            return 0

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = gray.mean()
        contrast = gray.std()

        blur_component = min(1.0, blur_score / 150.0)
        brightness_component = 1.0 - min(1.0, abs(brightness - 128.0) / 128.0)
        contrast_component = min(1.0, contrast / 64.0)
        quality = (blur_component * 0.5) + (brightness_component * 0.25) + (contrast_component * 0.25)
        return round(quality * 15)
    except Exception:
        size_score = min(15, max(1, frame_path.stat().st_size // 20000))
        return int(size_score)


def score_scene_context(frame_path: Path, subject: str | None = None) -> tuple[int, int, str]:
    study_prompts = build_study_prompts(subject)
    probabilities = classify_image_with_clip(frame_path, study_prompts)
    if not probabilities:
        detail = f" ({_clip_error})" if _clip_error else ""
        return 25, 0, f"이미지 맥락 모델을 사용할 수 없어 기본 장면 점수를 적용했습니다.{detail}"

    study_score = max(probabilities)

    scene_points = round(study_score * SCENE_SCORE_MAX)
    reason = f"study={study_score:.2f}"
    return scene_points, 0, reason


def build_study_prompts(subject: str | None) -> tuple[str, ...]:
    cleaned_subject = (subject or "").strip()
    if not cleaned_subject:
        return STUDY_PROMPTS

    dynamic_prompts = (
        f"a person studying {cleaned_subject}",
        f"study notes related to {cleaned_subject}",
        f"educational material about {cleaned_subject} on a screen",
        f"a textbook, lecture slide, or notebook for {cleaned_subject}",
    )
    return STUDY_PROMPTS + dynamic_prompts


def classify_image_with_clip(frame_path: Path, prompts: tuple[str, ...]) -> list[float]:
    global _clip_error

    try:
        model, processor, torch = get_clip_components()
        from PIL import Image

        image = Image.open(frame_path).convert("RGB")
        inputs = processor(
            text=list(prompts),
            images=image,
            return_tensors="pt",
            padding=True,
        )
        with torch.no_grad():
            outputs = model(**inputs)
            logits_per_image = outputs.logits_per_image
            probabilities = logits_per_image.softmax(dim=1)[0]

        return [float(value) for value in probabilities]
    except Exception as exc:
        _clip_error = _short_error(exc)
        return []


def get_clip_components():
    global _clip_model, _clip_processor, _clip_torch

    if _clip_model is None or _clip_processor is None or _clip_torch is None:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        local_files_only = _env_bool("CLIP_LOCAL_FILES_ONLY", False)
        _clip_torch = torch
        _clip_model = CLIPModel.from_pretrained(
            "openai/clip-vit-base-patch32",
            local_files_only=local_files_only,
        )
        _clip_processor = CLIPProcessor.from_pretrained(
            "openai/clip-vit-base-patch32",
            local_files_only=local_files_only,
        )
        _clip_model.eval()

    return _clip_model, _clip_processor, _clip_torch


def extract_text(frame_path: Path) -> str:
    global _ocr_error

    try:
        reader = get_ocr_reader()
        ocr_image_path = prepare_ocr_image(frame_path)
        result = reader.readtext(str(ocr_image_path), detail=0)
        return " ".join(text for text in result if text)
    except Exception as exc:
        _ocr_error = _short_error(exc)
        return ""


def prepare_ocr_image(frame_path: Path) -> Path:
    from PIL import Image, ImageEnhance, ImageOps

    image = Image.open(frame_path).convert("RGB")
    width, height = image.size
    max_dimension = max(width, height)

    if max_dimension > OCR_MAX_DIMENSION:
        scale = OCR_MAX_DIMENSION / max_dimension
        resized_size = (
            max(1, round(width * scale)),
            max(1, round(height * scale)),
        )
        image = image.resize(resized_size, Image.Resampling.LANCZOS)

    enhanced_image = ImageOps.autocontrast(image, cutoff=1)
    enhanced_image = ImageEnhance.Contrast(enhanced_image).enhance(1.25)
    enhanced_image = ImageEnhance.Sharpness(enhanced_image).enhance(1.35)
    ocr_path = frame_path.with_name(f"{frame_path.stem}_ocr.jpg")
    enhanced_image.save(ocr_path, format="JPEG", quality=90)
    return ocr_path


def get_ocr_reader():
    global _ocr_reader

    if _ocr_reader is None:
        import easyocr

        _ocr_reader = easyocr.Reader(["ko", "en"], gpu=False)

    return _ocr_reader


def score_subject_similarity(subject: str | None, extracted_text: str) -> tuple[int, str]:
    cleaned_subject = (subject or "").strip()
    cleaned_text = extracted_text.strip()
    if not cleaned_subject:
        return DEFAULT_TEXT_SCORE, "과목명이 없어 과목 관련성 점수를 부여하지 않았습니다."
    if not cleaned_text:
        if _ocr_error:
            return DEFAULT_TEXT_SCORE, f"OCR 텍스트가 없어 과목 관련성 점수를 부여하지 않았습니다. ({_ocr_error})"
        return DEFAULT_TEXT_SCORE, "OCR 텍스트가 없어 과목 관련성 점수를 부여하지 않았습니다."

    expanded_subject = expand_subject(cleaned_subject)
    similarity = calculate_text_similarity(expanded_subject, cleaned_text)
    if similarity is None:
        return keyword_fallback_score(expanded_subject, cleaned_text)

    semantic_score = score_similarity(similarity)
    evidence_score, evidence_reason = score_academic_text_evidence(cleaned_subject, cleaned_text)
    score = max(semantic_score, evidence_score)
    reason = f"text_similarity={similarity:.2f}"
    if evidence_reason:
        reason = f"{reason}, {evidence_reason}"

    return score, reason


def calculate_text_similarity(subject: str, extracted_text: str) -> float | None:
    try:
        model = get_embedding_model()
        chunks = chunk_text(extracted_text)
        embeddings = model.encode([subject, *chunks], normalize_embeddings=True)
        subject_embedding = embeddings[0]
        return max(float(subject_embedding @ chunk_embedding) for chunk_embedding in embeddings[1:])
    except Exception:
        return None


def score_similarity(similarity: float) -> int:
    # Sentence-transformer 유사도는 짧은 과목명 vs 긴 OCR 텍스트에서 0.3대도 꽤 의미 있는 관련성입니다.
    calibrated = (similarity - 0.12) / 0.38
    return round(max(0.0, min(1.0, calibrated)) * TEXT_SCORE_MAX)


def get_embedding_model():
    global _embedding_model

    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer(
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            local_files_only=True,
        )

    return _embedding_model


def keyword_fallback_score(subject: str, extracted_text: str) -> tuple[int, str]:
    subject_tokens = tokenize_text(subject)
    text_tokens = tokenize_text(extracted_text)
    evidence_score, evidence_reason = score_academic_text_evidence(subject, extracted_text)
    if not subject_tokens or not text_tokens:
        return evidence_score, "임베딩 모델을 사용할 수 없어 OCR 근거 기준으로 보정했습니다."

    overlap = len(subject_tokens & text_tokens)
    ratio = overlap / max(1, len(subject_tokens))
    score = DEFAULT_TEXT_SCORE + round(min(1.0, ratio) * 18)
    score = max(score, evidence_score)
    reason = "임베딩 모델을 사용할 수 없어 키워드 겹침 기준으로 보정했습니다."
    if evidence_reason:
        reason = f"{reason}, {evidence_reason}"
    return score, reason


def tokenize_text(value: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in value)
    return {token for token in normalized.split() if len(token) >= 2 and not token.isdigit()}


def expand_subject(subject: str) -> str:
    generic_context = (
        "lecture textbook notes workbook problem solving equation diagram concept "
        "definition theorem summary educational material study"
    )
    return f"{subject} {SUBJECT_ALIASES.get(subject.replace(' ', ''), '')} {SUBJECT_ALIASES.get(subject, '')} {generic_context}".strip()


def chunk_text(value: str, chunk_size: int = 320) -> list[str]:
    words = value.split()
    if not words:
        return [value]

    chunks = []
    for index in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[index:index + chunk_size]))
    return chunks


def score_academic_text_evidence(subject: str, extracted_text: str) -> tuple[int, str]:
    tokens = tokenize_text(extracted_text)
    formula_score, formula_reason = score_formula_evidence(subject, extracted_text)

    hint_matches = tokens & ACADEMIC_TEXT_HINTS
    if len(hint_matches) >= 4:
        return max(36, formula_score), f"academic_text_hints={len(hint_matches)}"
    if len(hint_matches) >= 2:
        return max(28, formula_score), f"academic_text_hints={len(hint_matches)}"
    if formula_score:
        return formula_score, formula_reason
    if len(tokens) >= 20:
        return 22, "OCR 학습 텍스트량이 충분합니다."

    return 0, ""


def score_formula_evidence(subject: str, extracted_text: str) -> tuple[int, str]:
    formula_markers = sum(
        extracted_text.count(marker)
        for marker in ("=", "+", "-", "V", "v", "λ", "∫", "∑", "→")
    )
    math_words = tokenize_text(extracted_text) & {
        "basis",
        "linear",
        "matrix",
        "multiplication",
        "scalar",
        "span",
        "vector",
        "곱셈",
        "벡터",
        "선형",
        "스칼라",
        "행렬",
    }

    if formula_markers >= 6 or len(math_words) >= 2:
        return 40, f"math_formula_evidence={formula_markers}"
    if formula_markers >= 3 or len(math_words) >= 1:
        return 32, f"math_formula_evidence={formula_markers}"

    return 0, ""


def has_strong_study_evidence(text_score: int) -> bool:
    return text_score >= STRONG_TEXT_SCORE


def save_representative_frame(frame_path: Path) -> str:
    output_dir = Path(tempfile.gettempdir()) / "logy_ai_frames"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{uuid.uuid4().hex}.jpg"
    shutil.copy2(frame_path, output_path)
    return str(output_path)
