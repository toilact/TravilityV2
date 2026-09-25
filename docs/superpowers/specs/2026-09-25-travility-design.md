# Travility — Design Spec (2026-09-25)

## Context
Đồ án nhóm (3–4 người, ~8–10 tuần): desktop app du lịch + bản đồ cho người Việt, dùng AI càng nhiều càng tốt, demo phải "wow" trước giảng viên. Thư mục `TravilityV2` đang trống (greenfield). Tài liệu này chốt ý tưởng + stack; bước kế tiếp là viết spec chính thức rồi implementation plan.

**Người dùng đã nói:** lõi là AI Trip Planner + Map; nhóm mạnh Python; dev bằng Gemini API, demo cho thầy bằng OpenAI (có 2500 credit); map Goong; frontend React.
**Giả định (sửa nếu sai):** không cần đăng nhập/tài khoản; lưu chuyến đi local; demo trực tiếp 10–15 phút trên 1 laptop.

## Sản phẩm
**Lõi — AI Trip Planner:** gõ/nói "Đi Đà Lạt 3 ngày, 3 triệu, thích cafe chill" → agent AI gọi tool tìm POI thật, tính đường, thời tiết, chi phí → lịch trình theo ngày hiện lên timeline + tuyến đường vẽ trên map 3D, camera bay qua từng điểm. Trong lúc AI "nghĩ", map hiện live các bước (đang tìm quán cafe… pin nhấp nháy) — đây là khoảnh khắc wow chính.

**Vệ tinh (thứ tự ưu tiên, cắt từ dưới lên nếu trễ):**
1. Sửa lịch trình bằng hội thoại — "ngày 2 mưa thì sao?", "bớt 500k", "thêm quán chay" → agent sửa đúng phần cần sửa, map animate điểm thay đổi; thời tiết thật (Open-Meteo, free, không key).
2. Giọng nói tiếng Việt — mic → STT → agent; trả lời bằng TTS.
3. Nhận diện ảnh — kéo thả ảnh "đi chỗ giống thế này" → vision mô tả phong cách → embedding → POI tương tự → ghim map.
4. Cinematic recap + xuất PDF — camera bay toàn tuyến kèm thuyết minh TTS; PDF lịch trình + bảng chi phí.

## Stack
| Lớp | Chọn |
|---|---|
| Desktop shell | **pywebview** (cửa sổ native) + đóng gói **PyInstaller** |
| Backend | **FastAPI** (uvicorn chạy thread nền, localhost), Python 3.12 |
| LLM | SDK `openai` duy nhất; đổi provider bằng env `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL` — dev: Gemini OpenAI-compatible endpoint, demo: OpenAI |
| STT/TTS | OpenAI (luôn, vì compat layer Gemini không đủ) |
| Embedding | Tạo 1 lần offline → lưu vào SQLite; tìm kiếm bằng numpy cosine (không cần vector DB với ~1000 POI) |
| Dữ liệu | **SQLite**: POI tự curate (tọa độ, ảnh, giá, giờ mở, mô tả, embedding) cho 3 thành phố trước (Đà Lạt, Hội An, Hà Nội), stretch 5 |
| Map | **MapLibre GL JS** + style/tiles **Goong** (đúng chủ quyền Hoàng Sa/Trường Sa), Goong Directions cho routing |
| Frontend | **React + Vite + Tailwind**, `react-map-gl` (maplibre) ; build static → pywebview load |
| Streaming | SSE từ FastAPI: `thinking` / `tool_call` / `itinerary` events |

## Kiến trúc
```
pywebview window ── React UI (chat | map 3D | timeline)
        │  HTTP + SSE (localhost)
FastAPI ├─ agent/     vòng lặp tool-calling, output = Itinerary JSON (structured output, validate bằng pydantic)
        ├─ tools      search_poi(city, query, filters) · get_route · get_weather · estimate_cost
        ├─ voice      STT / TTS
        ├─ vision     ảnh → mô tả → embedding → search_poi
        ├─ demo_cache record/replay theo hash(request) — bật khi mất mạng
        └─ db.sqlite  POI + embeddings + saved trips
scripts/build_dataset.py  thu thập POI (Goong Places + curate tay) → mô tả → embedding → SQLite
```
**Nguyên tắc chống bịa:** LLM chỉ được tham chiếu `poi_id` trả về từ tool; backend reject itinerary chứa id lạ và retry 1 lần. Tổng chi phí tính bằng code, không để LLM cộng.

**Itinerary schema:** `days[] → stops[] {poi_id, start_time, duration_min, est_cost, note}` + `total_cost`. Sửa lịch trình = gửi itinerary hiện tại + yêu cầu → itinerary mới; frontend diff để animate điểm đổi.

## Rủi ro & xử lý
- Gemini ≠ OpenAI về hành vi tool-calling → bộ ~15 prompt mẫu (golden set) chạy trên cả 2 provider; 2 tuần cuối chạy toàn bộ trên OpenAI.
- Mạng phòng bảo vệ yếu → demo_cache replay + dữ liệu POI/ảnh local.
- API key: `.env`, không commit; bản build demo nhúng key là chấp nhận được cho đồ án (ghi chú rõ).

## Phân công gợi ý (4 người)
A: Frontend + map/animation · B: Agent + tools + schema · C: Dataset pipeline + curate POI · D: Voice/vision/recap/PDF + đóng gói + demo_cache.

## Mốc (10 tuần)
T1–2 skeleton pywebview+FastAPI+map Goong, dataset 1 thành phố · T3–4 agent lõi end-to-end · T5–6 sửa hội thoại + voice · T7 vision · T8 recap/PDF · T9 chuyển OpenAI, golden set, polish · T10 kịch bản demo, đóng gói.

## Verification
- `pytest`: validate itinerary (poi_id tồn tại, tổng tiền khớp, thời gian không chồng), search_poi trả kết quả đúng thành phố.
- Golden set script: chạy 15 prompt trên cả 2 provider, báo % itinerary hợp lệ.
- Chạy app thật qua pywebview, diễn tập kịch bản demo có tắt mạng (replay).

