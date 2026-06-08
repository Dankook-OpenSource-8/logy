import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DEFAULT_MODEL_PATH = "models/study_classifier.pt"
MODEL_PATH = Path(os.getenv("STUDY_CLASSIFIER_MODEL_PATH", DEFAULT_MODEL_PATH))
SCENE_SCORE_MAX = 60
STUDY_PROBABILITY_THRESHOLD = 0.5


@dataclass(frozen=True)
class StudyClassifierResult:
    available: bool
    study_probability: float | None
    scene_score: int
    forbidden_penalty: int
    reason: str


def score_with_study_classifier(frame_path: Path) -> StudyClassifierResult:
    if not MODEL_PATH.exists():
        return StudyClassifierResult(
            available=False,
            study_probability=None,
            scene_score=0,
            forbidden_penalty=0,
            reason="fine_tuned_classifier=not_ready",
        )

    try:
        model, processor, torch, classifier_head = get_classifier_components()
        from PIL import Image

        image = Image.open(frame_path).convert("RGB")
        inputs = processor(images=image, return_tensors="pt")
        with torch.no_grad():
            image_features = get_image_features(model, inputs)
            logits = classifier_head(image_features)
            study_probability = float(torch.softmax(logits, dim=1)[0][1])

        scene_score, forbidden_penalty = score_probability(study_probability)
        return StudyClassifierResult(
            available=True,
            study_probability=study_probability,
            scene_score=scene_score,
            forbidden_penalty=forbidden_penalty,
            reason=f"fine_tuned_study_probability={study_probability:.2f}",
        )
    except Exception as exc:
        return StudyClassifierResult(
            available=False,
            study_probability=None,
            scene_score=0,
            forbidden_penalty=0,
            reason=f"fine_tuned_classifier_error={type(exc).__name__}",
        )


def score_probability(study_probability: float) -> tuple[int, int]:
    normalized = max(0.0, min(1.0, study_probability))
    if normalized < STUDY_PROBABILITY_THRESHOLD:
        return 0, 0

    scene_score = round(normalized * SCENE_SCORE_MAX)
    return scene_score, 0


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_classifier_components():
    import torch
    from transformers import CLIPModel, CLIPProcessor

    checkpoint = torch.load(MODEL_PATH, map_location="cpu")
    input_dim = checkpoint["input_dim"]
    model_name = checkpoint.get("clip_model_name", "openai/clip-vit-base-patch32")
    local_files_only = _env_bool("STUDY_CLASSIFIER_LOCAL_FILES_ONLY", False)

    clip_model = CLIPModel.from_pretrained(model_name, local_files_only=local_files_only)
    processor = CLIPProcessor.from_pretrained(model_name, local_files_only=local_files_only)
    classifier_head = torch.nn.Linear(input_dim, 2)
    classifier_head.load_state_dict(checkpoint["classifier_state_dict"])

    clip_model.eval()
    classifier_head.eval()
    return clip_model, processor, torch, classifier_head


def get_image_features(clip_model, inputs):
    features = clip_model.get_image_features(**inputs)
    if hasattr(features, "image_embeds"):
        features = features.image_embeds
    elif hasattr(features, "pooler_output"):
        features = features.pooler_output
    return features / features.norm(dim=-1, keepdim=True)
