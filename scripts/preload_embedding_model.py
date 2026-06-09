import os

from sentence_transformers import SentenceTransformer
from transformers import CLIPModel, CLIPProcessor

DEFAULT_EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"


def main() -> None:
    embedding_model_name = os.getenv("EMBEDDING_MODEL_NAME", DEFAULT_EMBEDDING_MODEL_NAME)
    clip_model_name = os.getenv("CLIP_MODEL_NAME", DEFAULT_CLIP_MODEL_NAME)

    SentenceTransformer(embedding_model_name)
    print(f"Preloaded embedding model: {embedding_model_name}")

    CLIPModel.from_pretrained(clip_model_name)
    CLIPProcessor.from_pretrained(clip_model_name)
    print(f"Preloaded CLIP model: {clip_model_name}")


if __name__ == "__main__":
    main()
