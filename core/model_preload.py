import os


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def preload_ai_models() -> None:
    if not _env_bool("PRELOAD_AI_MODELS", True):
        print("AI model preload skipped: PRELOAD_AI_MODELS is disabled")
        return

    try:
        from core.study_image_classifier import MODEL_PATH, get_classifier_components

        if MODEL_PATH.exists():
            get_classifier_components()
            print("Preloaded study classifier CLIP model")
        else:
            print("Study classifier preload skipped: model checkpoint not found")
    except Exception as exc:
        print(f"Study classifier preload failed: {type(exc).__name__}: {exc}")

    try:
        from core.ai_video_verification import get_embedding_model

        get_embedding_model()
        print("Preloaded embedding model")
    except Exception as exc:
        print(f"Embedding model preload failed: {type(exc).__name__}: {exc}")
