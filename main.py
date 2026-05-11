from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

app = FastAPI(title="Logy Backend")

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
