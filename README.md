# Travility

App desktop giúp người Việt lên kế hoạch du lịch trong nước bằng AI trên bản đồ.

## Tài liệu — đọc theo thứ tự

| # | File | Trả lời câu hỏi |
|---|---|---|
| 1 | [docs/PRD.md](docs/PRD.md) | Làm gì, vì sao, trạng thái từng tính năng, lộ trình, phân vai, thứ tự cắt |
| 2 | [CONTEXT.md](CONTEXT.md) | Thuật ngữ — dùng đúng trong code, UI, issue |
| 3 | [docs/2026-09-25-hien-trang-app.md](docs/2026-09-25-hien-trang-app.md) | Code hiện tại chạy thế nào (luồng SSE, UI) |
| 4 | [docs/adr/](docs/adr/) | Quyết định kiến trúc và lý do |
| 5 | [docs/superpowers/specs/](docs/superpowers/specs/) | Thiết kế kỹ thuật gốc (Stack, Kiến trúc) |
| 6 | [docs/superpowers/plans/](docs/superpowers/plans/) | Kế hoạch triển khai từng giai đoạn (Plan 1 ✅) |
| 7 | [docs/agents/](docs/agents/) | Quy ước issue tracker (GitHub + `gh`) và nhãn triage |

Khi các tài liệu mâu thuẫn: **PRD thắng spec**; CONTEXT.md thắng về cách gọi tên.

## Phân vai & vùng code

Người phụ trách và danh sách issue: PRD §12. Mỗi vai là người review chính cho vùng code của mình.

| Vai | Phụ trách | Vùng code |
|---|---|---|
| A — Nhật | Client React, bản đồ/animation, UI mới | `client/`, `desktop/` |
| B — Thành | Agent, tools, rules, Revision | `server/app/agent.py`, `rules.py`, `trips.py`, `domain.py` |
| C — Quân | Dữ liệu Place, import, pgvector, Goong Matrix | `data/places/`, `server/scripts/`, `server/app/places.py` |
| D — Tùng | Auth, voice/vision/recap/PDF, đóng gói, demo_cache | `server/app/auth.py`, `forecast.py`, `llm.py`, `docker-compose.yml` |

## Quy trình làm việc

1. Việc được tách từ PRD thành GitHub Issue (`/to-issues`), gắn nhãn theo [docs/agents/triage-labels.md](docs/agents/triage-labels.md).
2. Mỗi giai đoạn lớn có một plan trong `docs/superpowers/plans/` trước khi code.
3. Làm trên nhánh riêng → PR vào `main` → test xanh (xem Commands) → người phụ trách vùng code review.
4. Đổi yêu cầu → sửa PRD; thêm/đổi thuật ngữ → sửa CONTEXT.md; quyết định kiến trúc mới → thêm ADR.

## Chạy lần đầu

```bash
cp server/.env.example server/.env        # điền LLM_API_KEY, EMBED_API_KEY, JWT_SECRET
python -c "import secrets;print(secrets.token_urlsafe(32))"  # dán vào JWT_SECRET ở trên
cp client/.env.example client/.env        # điền key Goong
docker compose up -d --build              # Postgres + API ở http://localhost:8000
cd server && uv sync && uv run python -m scripts.import_places ../data/places
cd ../client && npm install && npm run build
cd ../desktop && uv sync && uv run python main.py
```

## Phát triển

- Test server: `docker compose up -d db && cd server && uv run pytest`
- Test client: `cd client && npm test`
- Client dev: `cd client && npm run dev`, rồi `cd desktop && uv run python main.py http://localhost:5173`
- Đổi AI sang OpenAI khi demo: trong `server/.env` đặt `LLM_BASE_URL=https://api.openai.com/v1`, `LLM_API_KEY`, `LLM_MODEL` rồi `docker compose up -d --build api`

## Trạng thái

Plan 1 (nền tảng + AI Trip Planner lõi) ✅ trên nhánh `feat/plan-1-core`. Tiếp theo: Plan 2 + UI mới (PRD §12).
