import os

from fastapi import HTTPException, status
from core.supabase_client import get_supabase_client

VIDEO_BUCKET_NAME = os.getenv("SUPABASE_VIDEO_BUCKET", "videos")


def upload_video(file_path: str, file_bytes: bytes, content_type: str) -> str:
    # videos 버킷에 영상 파일을 업로드하고 외부 접근 가능한 URL을 반환합니다.
    supabase = get_supabase_client()

    try:
        supabase.storage.from_(VIDEO_BUCKET_NAME).upload(
            file_path,
            file_bytes,
            file_options={
                "content-type": content_type,
                "upsert": "false",
            },
        )
        return supabase.storage.from_(VIDEO_BUCKET_NAME).get_public_url(file_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase Storage 업로드에 실패했습니다: {exc}",
        ) from exc
