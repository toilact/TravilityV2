# Travility

Desktop app du lịch + bản đồ cho người Việt, AI Trip Planner làm lõi. Spec: `docs/superpowers/specs/2026-09-25-travility-design.md`.

## Agent skills

### Issue tracker

Issues nằm ở GitHub Issues của repo (dùng `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Dùng 5 nhãn mặc định: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` ở gốc repo. See `docs/agents/domain.md`.

## Commands

- Server test: `docker compose up -d db && cd server && uv run pytest`
- Client test/build: `cd client && npm test && npm run build`
- Import Place: `cd server && uv run python -m scripts.import_places ../data/places`
- Desktop: `cd desktop && uv run python main.py [url]`
