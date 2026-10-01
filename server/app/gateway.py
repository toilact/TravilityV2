"""llm-gateway: proxy giao thức OpenAI đứng giữa các service và provider (spec scale §6).

Cache theo hash(request), giới hạn lượt gọi theo provider, chuyển sang provider phụ khi provider chính lỗi.
Chạy: uvicorn app.gateway:app
"""
import hashlib
import json

import httpx
from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse, Response
from redis.exceptions import RedisError

from app import kv
from app.config import settings

CHAT, EMBED = "chat/completions", "embeddings"

app = FastAPI(title="Travility llm-gateway")
http = httpx.Client(timeout=60)  # test thay bằng MockTransport


def _redis(op: str, *args, default=None, **kw):
    """Gọi một lệnh Redis; không cấu hình hoặc lỗi → default (Redis lỗi thì bỏ qua, không chặn — spec §10)."""
    c = kv.client()
    if c is None:
        return default
    try:
        return getattr(c, op)(*args, **kw)
    except RedisError:
        return default


def _stat(name: str) -> None:
    _redis("incr", f"gw:stat:{name}")


def _synthetic(status: int, message: str) -> httpx.Response:
    """Lỗi do gateway tự sinh, cùng dạng thân lỗi của OpenAI để SDK phía gọi đọc được."""
    return httpx.Response(status, json={"error": {"message": message, "type": "gateway_error"}})


def _post(base: str, api_key: str, path: str, body: dict) -> httpx.Response:
    _stat("provider_call")
    try:
        return http.post(f"{base.rstrip('/')}/{path}", json=body, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as e:
        return _synthetic(504, f"provider không phản hồi ({type(e).__name__})")


def _call(path: str, body: dict) -> httpx.Response:
    if path == EMBED:
        return _post(settings.embed_base_url, settings.embed_api_key, path, body)
    return _post(settings.llm_base_url, settings.llm_api_key, path, body)


def _cache_key(path: str, body: dict) -> str:
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "gw:cache:" + hashlib.sha256(f"{path}\n{canon}".encode()).hexdigest()


def _handle(path: str, body: dict) -> Response:
    if body.get("stream"):
        return JSONResponse({"error": {"message": "llm-gateway không hỗ trợ stream"}}, status_code=400)
    mode, key = settings.gateway_cache, _cache_key(path, body)
    if mode != "off":
        hit = _redis("get", key)
        if hit is not None:
            _stat("hit")
            return Response(hit, media_type="application/json", headers={"X-Cache": "hit"})
        if mode == "replay":
            return JSONResponse({"error": {"message": "llm-gateway đang ở chế độ replay và chưa ghi phản hồi "
                                                      "cho request này"}}, status_code=503)
        _stat("miss")
    r = _call(path, body)
    if r.status_code == 200 and mode == "on":
        ttl = settings.gateway_chat_ttl if path == CHAT else 0  # embedding không hết hạn
        _redis("set", key, r.text, ex=ttl or None)
    return Response(r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type", "application/json"), headers={"X-Cache": "miss"})


@app.post("/v1/chat/completions")
def chat_completions(body: dict = Body(...)):
    return _handle(CHAT, body)


@app.post("/v1/embeddings")
def embeddings(body: dict = Body(...)):
    return _handle(EMBED, body)


@app.get("/health")
def health():
    return {"ok": True}
