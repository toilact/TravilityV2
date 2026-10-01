import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import gateway, kv
from app.config import settings

OK = {"id": "c1", "choices": [{"message": {"role": "assistant", "content": "xin chào"}}]}
CHAT = {"model": "m1", "messages": [{"role": "user", "content": "hi"}]}
EMB = {"model": "e1", "input": ["cà phê"], "dimensions": 768}

client = TestClient(gateway.app)


class Upstream:
    """Provider giả: replies[host] = (status | Exception, body); mặc định 200 OK."""

    def __init__(self):
        self.calls, self.replies = [], {}

    def __call__(self, request):
        self.calls.append(request)
        status, body = self.replies.get(request.url.host, (200, OK))
        if isinstance(status, Exception):
            raise status
        return httpx.Response(status, text=body) if isinstance(body, str) else httpx.Response(status, json=body)

    @property
    def hosts(self):
        return [c.url.host for c in self.calls]


@pytest.fixture
def up(monkeypatch, rds):
    u = Upstream()
    monkeypatch.setattr(gateway, "http", httpx.Client(transport=httpx.MockTransport(u)))
    for k, v in dict(llm_base_url="https://primary.test/v1/", llm_api_key="k1", llm_model="m1",
                     embed_base_url="https://embed.test/v1", embed_api_key="ke",
                     llm2_base_url="", llm2_api_key="", llm2_model="",
                     gateway_cache="on", gateway_chat_ttl=86400, llm_rpm=0).items():
        monkeypatch.setattr(settings, k, v)
    return u


def post(body=CHAT):
    return client.post("/v1/chat/completions", json=body)


def ask(i):
    """Một request chat khác nhau cho mỗi i (không trúng cache của nhau)."""
    return post({**CHAT, "messages": [{"role": "user", "content": f"câu {i}"}]})


def test_health():
    assert client.get("/health").json() == {"ok": True}


def test_proxies_with_gateway_key_not_callers(up):
    r = client.post("/v1/chat/completions", json=CHAT, headers={"Authorization": "Bearer cua-ben-goi"})
    assert r.status_code == 200 and r.json() == OK and r.headers["x-cache"] == "miss"
    req = up.calls[0]
    assert str(req.url) == "https://primary.test/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer k1"
    assert json.loads(req.content) == CHAT


def test_same_request_hits_cache_regardless_of_key_order(up, rds):
    post()
    r = post({"messages": CHAT["messages"], "model": "m1"})
    assert r.json() == OK and r.headers["x-cache"] == "hit" and len(up.calls) == 1
    assert rds.mget("gw:stat:hit", "gw:stat:miss", "gw:stat:provider_call") == ["1", "1", "1"]


def test_different_request_misses(up):
    ask(1)
    assert ask(2).headers["x-cache"] == "miss" and len(up.calls) == 2


def test_chat_expires_embedding_does_not(up, rds):
    post()
    r = client.post("/v1/embeddings", json=EMB)
    assert r.status_code == 200
    assert str(up.calls[1].url) == "https://embed.test/v1/embeddings"
    assert up.calls[1].headers["authorization"] == "Bearer ke"
    ttls = sorted(rds.ttl(k) for k in rds.keys("gw:cache:*"))
    assert ttls[0] == -1 and 0 < ttls[1] <= 86400


def test_chat_ttl_zero_never_expires(up, rds, monkeypatch):
    monkeypatch.setattr(settings, "gateway_chat_ttl", 0)
    post()
    assert [rds.ttl(k) for k in rds.keys("gw:cache:*")] == [-1]


def test_off_always_calls_provider(up, rds, monkeypatch):
    monkeypatch.setattr(settings, "gateway_cache", "off")
    post()
    post()
    assert len(up.calls) == 2 and rds.keys("gw:cache:*") == []


def test_replay_serves_recorded_and_rejects_unrecorded(up, monkeypatch):
    post()
    monkeypatch.setattr(settings, "gateway_cache", "replay")
    assert post().json() == OK
    r = ask(1)
    assert r.status_code == 503 and "chưa ghi" in r.json()["error"]["message"]
    assert len(up.calls) == 1  # replay không bao giờ gọi provider


def test_provider_error_passed_through_not_cached(up):
    up.replies["primary.test"] = (400, {"error": {"message": "bad"}})
    r = post()
    assert r.status_code == 400 and r.json() == {"error": {"message": "bad"}}
    post()
    assert len(up.calls) == 2


def test_non_json_provider_error_passed_through(up):
    up.replies["primary.test"] = (502, "<html>Bad Gateway</html>")
    r = post()
    assert r.status_code == 502 and r.text == "<html>Bad Gateway</html>"


def test_provider_unreachable_gives_504(up):
    up.replies["primary.test"] = (httpx.ConnectError("offline"), None)
    r = post()
    assert r.status_code == 504 and "không phản hồi" in r.json()["error"]["message"]


def test_stream_rejected(up):
    r = post({**CHAT, "stream": True})
    assert r.status_code == 400 and up.calls == []


def test_redis_down_still_answers(up, monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://localhost:1/0")
    monkeypatch.setattr(kv, "_client", None)
    assert post().status_code == 200 and post().headers["x-cache"] == "miss"
    assert len(up.calls) == 2
