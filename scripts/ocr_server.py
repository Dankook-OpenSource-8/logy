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
        return reader.readtext(image_path, detail=0), None
    except Exception as first_error:
        try:
            texts = reader.readtext(
                image_path,
                detail=0,
                canvas_size=1280,
                min_size=40,
                bbox_min_size=12,
                text_threshold=0.6,
                low_text=0.3,
            )
            return texts, f"retried_after={type(first_error).__name__}"
        except Exception as second_error:
            return [], f"{type(first_error).__name__}: {first_error}; retry={type(second_error).__name__}: {second_error}"
