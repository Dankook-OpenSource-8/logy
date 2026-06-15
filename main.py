from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from fastapi.security import HTTPBearer

from api.routes import router
from core.model_preload import preload_ai_models

app = FastAPI(title="Logy Backend")

security = HTTPBearer()

# 프론트엔드에서 백엔드 API를 호출할 수 있도록 CORS를 허용합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 분리된 API 라우터를 FastAPI 앱에 연결합니다.
app.include_router(router)


@app.on_event("startup")
def preload_models_on_startup() -> None:
    preload_ai_models()


@app.get("/auth-test", tags=["Test"])
def test_authorization(token=Depends(security)):
    return {
        "message": "Swagger 인증 설정 성공!", 
        "your_token": token.credentials
    }
