import time
from pathlib import Path
from tempfile import NamedTemporaryFile

import easyocr
from fastapi import FastAPI, File, UploadFile


app = FastAPI(title="Logy OCR Server")
reader = easyocr.Reader(["ko", "en"], gpu=False)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ocr")
async def read_ocr(file: UploadFile = File(...)) -> dict[str, object]:
    started_at = time.perf_counter()
    suffix = Path(file.filename or "frame.jpg").suffix or ".jpg"

    with NamedTemporaryFile(delete=True, suffix=suffix) as temp_file:
        temp_file.write(await file.read())
        temp_file.flush()
        texts, error = read_text_safely(temp_file.name)

    return {
        "text": " ".join(text for text in texts if text),
        "texts": [text for text in texts if text],
        "elapsed_seconds": round(time.perf_counter() - started_at, 2),
        "error": error,
    }


def read_text_safely(image_path: str) -> tuple[list[str], str | None]:
    try:
        return read_text_variants(image_path), None
    except Exception as first_error:
        try:
            texts = read_text_variants(image_path, relaxed_only=True)
            return texts, f"retried_after={type(first_error).__name__}"
        except Exception as second_error:
            return [], f"{type(first_error).__name__}: {first_error}; retry={type(second_error).__name__}: {second_error}"


def read_text_variants(image_path: str, relaxed_only: bool = False) -> list[str]:
    attempts = (
        {"detail": 0},
        {
            "detail": 0,
            "canvas_size": 1280,
            "min_size": 20,
            "bbox_min_size": 8,
            "text_threshold": 0.4,
            "low_text": 0.2,
        },
        {
            "detail": 0,
            "canvas_size": 1920,
            "min_size": 10,
            "bbox_min_size": 5,
            "text_threshold": 0.3,
            "low_text": 0.1,
        },
    )
    selected_attempts = attempts[1:] if relaxed_only else attempts
    best_result: list[str] = []
    for options in selected_attempts:
        result = [text for text in reader.readtext(image_path, **options) if text]
        if len(" ".join(result)) > len(" ".join(best_result)):
            best_result = result
        if len(best_result) >= 8 or len(" ".join(best_result)) >= 120:
            break
    return best_result
