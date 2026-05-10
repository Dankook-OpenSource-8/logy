import os
from dotenv import load_dotenv

# .env 파일을 읽어옵니다.
load_dotenv()

class Settings:
    # 환경변수에서 값을 가져오고, 없으면 에러를 방지하기 위해 기본값 None 설정
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")

# 어디서든 이 객체를 통해 설정을 쓸 수 있게 인스턴스 생성
settings = Settings()