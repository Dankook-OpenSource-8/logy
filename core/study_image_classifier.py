import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DEFAULT_MODEL_PATH = "models/study_classifier.pt"
MODEL_PATH = Path(os.getenv("STUDY_CLASSIFIER_MODEL_PATH", DEFAULT_MODEL_PATH))


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
            image_features = model.get_image_features(**inputs)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
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
    scene_score = round(normalized * 45)
    forbidden_penalty = round((1.0 - normalized) * 40)
    return scene_score, forbidden_penalty


@lru_cache
def get_classifier_components():
    import torch
    from transformers import CLIPModel, CLIPProcessor

    checkpoint = torch.load(MODEL_PATH, map_location="cpu")
    input_dim = checkpoint["input_dim"]
    model_name = checkpoint.get("clip_model_name", "openai/clip-vit-base-patch32")

    clip_model = CLIPModel.from_pretrained(model_name, local_files_only=True)
    processor = CLIPProcessor.from_pretrained(model_name, local_files_only=True)
    classifier_head = torch.nn.Linear(input_dim, 2)
    classifier_head.load_state_dict(checkpoint["classifier_state_dict"])

    clip_model.eval()
    classifier_head.eval()
    return clip_model, processor, torch, classifier_head
