import os
import sys
from pathlib import Path

from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ai_video_verification import EMBEDDING_MODEL_NAME


def main() -> None:
    model_name = os.getenv("EMBEDDING_MODEL_NAME", EMBEDDING_MODEL_NAME)
    SentenceTransformer(model_name)
    print(f"Preloaded embedding model: {model_name}")


if __name__ == "__main__":
    main()
