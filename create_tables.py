# create_tables.py
from database import engine, Base
import models  # models.py의 내용을 인식하기 위해 가져옵니다.

def create_database():
    print("데이터베이스 연결 및 테이블 생성을 시작합니다.")
    
    try:
        # DB에 실제 테이블 생성
        Base.metadata.create_all(bind=engine)
        print("성공: 모든 테이블이 데이터베이스에 생성되었습니다.")
        
    except Exception as e:
        print(f"오류: 테이블 생성 중 문제가 발생했습니다.\n내용: {e}")

if __name__ == "__main__":
    create_database()