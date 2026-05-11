from functools import lru_cache

from supabase import create_client, Client
from core.config import settings


@lru_cache
def get_supabase_client() -> Client:
    # .env 설정값으로 Supabase 클라이언트를 생성합니다.
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise ValueError(
            "❌ Supabase URL 또는 Key가 .env 파일에 없습니다! "
            ".env.example 파일을 참고해서 설정을 완료해주세요."
        )

    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
