from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import auth, trips
from app.config import settings
from app.db import apply_schema, connect

_DEFAULT_JWT_SECRETS = {"dev-secret-change-me", "doi-chuoi-nay-thanh-chuoi-ngau-nhien-dai"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.jwt_secret in _DEFAULT_JWT_SECRETS:
        raise RuntimeError("JWT_SECRET chưa được đặt — sửa server/.env")
    with connect() as conn:
        apply_schema(conn)
    yield


app = FastAPI(title="Travility", lifespan=lifespan)
# Client desktop gửi JWT qua header, không dùng cookie → cho mọi origin là an toàn.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(trips.router)


@app.get("/health")
def health():
    return {"ok": True}
