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
        texts = reader.readtext(temp_file.name, detail=0)

    return {
        "text": " ".join(text for text in texts if text),
        "texts": [text for text in texts if text],
        "elapsed_seconds": round(time.perf_counter() - started_at, 2),
    }
