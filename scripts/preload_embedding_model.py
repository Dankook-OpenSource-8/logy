import os

from sentence_transformers import SentenceTransformer

from core.ai_video_verification import EMBEDDING_MODEL_NAME


def main() -> None:
    model_name = os.getenv("EMBEDDING_MODEL_NAME", EMBEDDING_MODEL_NAME)
    SentenceTransformer(model_name)
    print(f"Preloaded embedding model: {model_name}")


if __name__ == "__main__":
    main()
