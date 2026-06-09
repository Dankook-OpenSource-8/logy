import os

from sentence_transformers import SentenceTransformer

DEFAULT_EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def main() -> None:
    model_name = os.getenv("EMBEDDING_MODEL_NAME", DEFAULT_EMBEDDING_MODEL_NAME)
    SentenceTransformer(model_name)
    print(f"Preloaded embedding model: {model_name}")


if __name__ == "__main__":
    main()
