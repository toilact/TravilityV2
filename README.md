# Travility

App desktop giúp người Việt lên kế hoạch du lịch trong nước bằng AI trên bản đồ. Xem `CONTEXT.md` (thuật ngữ), `docs/superpowers/specs/` (spec), `docs/adr/` (quyết định kiến trúc).

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
