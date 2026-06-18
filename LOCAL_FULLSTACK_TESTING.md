# Local Fullstack Testing

Use this branch when you want Expo to talk to your local FastAPI server instead of Railway.

## Backend

1. Copy the example env:

```bash
cp .env.local.example .env
```

2. Fill in `DATABASE_URL` and Supabase values for a local/test database.

3. Start the backend:

```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

4. Optional OCR server:

```bash
.venv/bin/uvicorn scripts.ocr_server:app --host 0.0.0.0 --port 8001 --reload
```

If you run OCR separately, set:

```text
OCR_SERVER_URL=http://127.0.0.1:8001/ocr
```

If `OCR_SERVER_URL` is empty, the backend will use local EasyOCR directly.

## Expo App

When testing on a physical phone, do not use `localhost` for the API URL. Use your Mac's LAN IP:

```text
EXPO_PUBLIC_API_BASE_URL=http://192.168.x.x:8000
```

Railway is not used as long as the Expo app points at the local backend URL.
