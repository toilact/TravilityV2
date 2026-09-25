from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import apply_schema, connect


@asynccontextmanager
async def lifespan(_: FastAPI):
    with connect() as conn:
        apply_schema(conn)
    yield


app = FastAPI(title="Travility", lifespan=lifespan)
# Client desktop gửi JWT qua header, không dùng cookie → cho mọi origin là an toàn.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True}
