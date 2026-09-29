# Travility

App desktop giúp người Việt lên kế hoạch du lịch trong nước bằng AI trên bản đồ.

## Tài liệu — đọc theo thứ tự

| # | File | Trả lời câu hỏi |
|---|---|---|
| 1 | [docs/PRD.md](docs/PRD.md) | Làm gì, vì sao, trạng thái từng tính năng, lộ trình, phân vai, thứ tự cắt |
| 2 | [CONTEXT.md](CONTEXT.md) | Thuật ngữ — dùng đúng trong code, UI, issue |
| 3 | [docs/2026-09-25-hien-trang-app.md](docs/2026-09-25-hien-trang-app.md) | Code hiện tại chạy thế nào (luồng SSE, UI) |
| 4 | [docs/adr/](docs/adr/) | Quyết định kiến trúc và lý do |
| 5 | [docs/superpowers/specs/](docs/superpowers/specs/) | Thiết kế kỹ thuật gốc (Stack, Kiến trúc) + spec cá nhân hoá Trip |
| 6 | [docs/superpowers/plans/](docs/superpowers/plans/) | Kế hoạch triển khai từng giai đoạn (Plan 1 ✅, cá nhân hoá lát 1 ✅) |
| 7 | [docs/agents/](docs/agents/) | Quy ước issue tracker (GitHub + `gh`) và nhãn triage |

Khi các tài liệu mâu thuẫn: **PRD thắng spec**; CONTEXT.md thắng về cách gọi tên.

## Phân vai & vùng code

Người phụ trách và danh sách issue: PRD §12. Mỗi vai là người review chính cho vùng code của mình.

| Vai | Phụ trách | Vùng code | Issue |
|---|---|---|---|
| A — Nhật (@minhatt1901) | Client React, bản đồ/animation, UI mới | `client/`, `desktop/` | #2 #3 #4 #8 #9 #16 #23 #28 |
| B — Thành (@toilact) | Agent, tools, rules, Revision | `server/app/agent.py`, `rules.py`, `trips.py`, `domain.py` | #6 #7 #17 #18 #22 #24–#27 #29 |
| C — Quân (@skyduyquan2-sudo) | Dữ liệu Place, import, pgvector | `data/places/`, `server/scripts/`, `server/app/places.py` | #5 #19 #20 #21 |
| D — Tùng (@nguyentung206) | Auth, vision/PDF, đóng gói, demo_cache | `server/app/auth.py`, `forecast.py`, `llm.py`, `docker-compose.yml` | #10–#15 |

Mọi issue đang mở đã được assign trên GitHub; xem việc của mình: `gh issue list --assignee @me`.

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

- API từ chối khởi động nếu `JWT_SECRET` còn là giá trị mẫu.
- Gemini gói free: dùng `LLM_MODEL=gemini-3.5-flash-lite` (bản `2.5-flash` chỉ 5 request/phút, lập lịch sẽ báo "Không kết nối được AI"). Lỗi AI thật nằm trong `docker compose logs api`.
- Hết credit OpenAI cho embedding: dùng khối Gemini đã comment sẵn trong `server/.env.example`, rồi chạy lại `import_places`.
- Đăng nhập lần đầu: bấm **Đăng ký** trong app (email bất kỳ, mật khẩu ≥ 8 ký tự).

## Phát triển

- Test server: `docker compose up -d db && cd server && uv run pytest`
- Test client: `cd client && npm test`
- Client dev: `cd client && npm run dev`, rồi `cd desktop && uv run python main.py http://localhost:5173`
- Sửa code server: `docker compose up -d --build api`. Sửa `server/.env`: `docker compose up -d --force-recreate api`.
- Sửa `data/places/*.json`: chạy lại `import_places` (upsert, không mất dữ liệu).
- Build client xong mà app desktop vẫn trắng / chạy bản cũ: tắt app, `rm -rf ~/Library/Caches/python3` (WebKit giữ cache bản build cũ), mở lại.
- Đổi AI sang OpenAI khi demo: trong `server/.env` đặt `LLM_BASE_URL=https://api.openai.com/v1`, `LLM_API_KEY`, `LLM_MODEL` rồi `docker compose up -d --force-recreate api`

## Trạng thái

- ✅ Plan 1: nền tảng + AI Trip Planner lõi (PR #1).
- 🟡 Cá nhân hoá Trip lát 1 (PR #30, chờ review): AI hỏi lại một vòng khi thiếu phương tiện / giờ đến–về (event SSE `clarify` → `POST /trips/{id}/plan`), Conflict giờ đến/về, Hub sân bay/bến xe, xe máy/ô tô riêng, chat gắn với Trip (tin nhắn sau gửi `trip_id`, lập lại thành version mới, nút "Chuyến mới"), bắt buộc đủ 3 bữa/ngày, thêm 27 Place Đà Lạt (`unverified`, chờ Quân kiểm chứng).
- ⏳ Tiếp theo: Revision đầy đủ (#22, #24, #25), lát 2–3 của spec (chỗ ở đã đặt, điểm bắt buộc ghé, Traveler Profile #18), UI mới (#16). Lộ trình: PRD §12.
- Tài liệu hiện trạng `docs/2026-09-25-hien-trang-app.md` viết trước lát 1 — luồng SSE mới (event `clarify`, `trip_id`) xem spec cá nhân hoá §3.
