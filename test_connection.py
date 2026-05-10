import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

# URL 끝에 /rest/v1/ 등이 붙어있으면 제거해주는 안전장치
if url and "/rest/v1/" in url:
    url = url.split("/rest/v1/")[0]

try:
    print(f"📡 연결 시도 중: {url}")
    supabase = create_client(url, key)
    
    # 단순히 버킷 목록만 가져와보기
    response = supabase.storage.list_buckets()
    print("✅ 연결 성공! 내 버킷 목록:")
    for bucket in response:
        print(f"- {bucket.name}")
        
except Exception as e:
    print("❌ 진짜 에러 내용:")
    print(e) # 이제 'error'라고 안 뜨고 자세히 뜰 거예요