from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Float, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# 사용자 정보를 저장하는 모델
# 자체 로그인, 카카오 로그인, 위치 및 외출 모드 정보를 포함함
class User(Base):
    __tablename__ = "users"
    # 1. 고유 번호 (자동 생성)
    id = Column(Integer, primary_key=True, index=True)
    
    # 2. 자체 로그인 관련
    username = Column(String, unique=True, nullable=True)  #사용자명 (자체 로그인만 사용)
    password = Column(String, nullable=True)  #비밀번호 (자체 로그인만 사용)
    
    # 3. 공통 정보
    email = Column(String, unique=True, nullable=True)  #이메일
    phone_number = Column(String, unique=True, nullable=True)  #전화번호 (온보딩에서 입력 가능)
    latitude = Column(Float, nullable=True)  #사용자 위도 (지역 기반 나눔용)
    longitude = Column(Float, nullable=True)  #사용자 경도 (지역 기반 나눔용)
    is_away_mode = Column(Boolean, default=False)  #외출 모드 활성화 여부
    away_end_date = Column(Date, nullable=True)  #외출 종료 날짜
    
    # 4. 카카오 로그인 관련
    kakao_id = Column(String, unique=True, nullable=True)  #카카오 고유 ID (카카오 로그인만 사용)
    
    # 5. 로그인 방식 구분
    login_type = Column(String, nullable=False)  #로그인 방식: "local" 또는 "kakao"
    
    # 6. 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())  #가입일
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())  #정보 수정일
    
    # 7. 관계 설정
    ingredients = relationship("Ingredient", back_populates="user")
    sharings = relationship("Sharing", back_populates="user")

# 식재료 정보를 저장하는 모델
# 신선도, 상태, 소비/폐기, 보관 타입 필드를 포함함
class Ingredient(Base):
    __tablename__ = "ingredients"
    # 1. 고유 번호 (자동 생성)
    id = Column(Integer, primary_key=True, index=True)
    
    # 1-1. 사용자 연결
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  #사용자 ID
    
    # 2. 필수 데이터 
    name = Column(String, nullable=False)   #식재료명
    price = Column(Integer, nullable=False)  #가격
    quantity = Column(Integer, default=1)   #수량 
    expiration_date = Column(Date, nullable=False) #유통기한 (D-Day 정렬용)
    decay_weight = Column(Float, nullable=True)  #부패 가중치 (신선도 대시보드)
    status = Column(String, nullable=False, server_default="fresh")  #fresh/warning/spoiled
    is_consumed = Column(Boolean, default=False)  #섭취 여부
    is_discarded = Column(Boolean, default=False)  #폐기 여부
    storage_type = Column(String, nullable=True)   #보관 타입 (냉장/냉동)
    # 3. 추가 정보
    category = Column(String, nullable=True)   #카테고리
    created_at = Column(DateTime(timezone=True), server_default=func.now())  #등록일
    
    # 4. 관계 설정
    user = relationship("User", back_populates="ingredients")
    sharings = relationship("Sharing", back_populates="ingredient")

# 나눔 정보를 저장하는 모델
# 식재료, 나눔 등록자, 반경 제한 정보를 포함함
class Sharing(Base):
    __tablename__ = "sharings"
    id = Column(Integer, primary_key=True, index=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)  #어떤 식재료인지
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  #나눔 등록자
    radius_limit = Column(Integer, nullable=False, default=100)  #반경 제한 (미터)
    is_completed = Column(Boolean, default=False)  #나눔 완료 여부
    
    ingredient = relationship("Ingredient", back_populates="sharings")
    user = relationship("User", back_populates="sharings")
