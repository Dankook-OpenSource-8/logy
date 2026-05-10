from supabase import create_client, Client
from core.config import settings

def get_supabase_client() -> Client:
    """
    .env에 설정된 정보를 바탕으로 Supabase 클라이언트를 생성합니다.
    """
    # 설정값이 비어있으면 팀원들에게 친절하게 에러를 알려줌
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise ValueError(
            "❌ Supabase URL 또는 Key가 .env 파일에 없습니다! "
            ".env.example 파일을 참고해서 설정을 완료해주세요."
        )
        
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# 어디서든 'from core.supabase_client import supabase'로 
# 바로 쓸 수 있게 인스턴스를 하나 만들어둡니다.
supabase = get_supabase_client()