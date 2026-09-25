# Travility — Hiện trạng app sau Plan 1 (2026-09-25)

> Ảnh chụp hiện trạng code tại cuối Plan 1, dùng làm phụ lục cho [PRD.md](PRD.md). Các quyết định mới (UI map full, Revision, lộ trình…) nằm trong PRD; mục "Bước tiếp theo" và 3.6 dưới đây đã được PRD thay thế.

Thuật ngữ in đậm theo [CONTEXT.md](../CONTEXT.md). Spec: [travility-design.md](superpowers/specs/2026-09-25-travility-design.md).

## 1. Tiến độ

- **Plan 1 (nền tảng + AI Trip Planner lõi): xong 13/13 task** trên nhánh `feat/plan-1-core` (15 commit, chưa merge `main`, chưa push).
- Test: server 58 test pass (pytest + Postgres Docker), client 2 test pass, build OK.
- **Chưa chạy thử E2E** với LLM thật qua app desktop.
- **Dữ liệu:** chỉ 10 Place Đà Lạt (spec cần 150–300 Place/Destination × 3 Destination) → lỗ hổng lớn nhất cho demo.
- **Chưa làm:**
  - Plan 2 — Revision, Pinned Stop, undo phiên bản, Traveler Profile
  - Plan 3 — giọng nói, Inspiration Photo
  - Plan 4 — Google login, quên mật khẩu, cinematic recap, PDF
  - Plan 5 — demo_cache, golden set, PyInstaller, đủ 3 Destination

### Bước tiếp theo đề xuất
1. Chạy E2E: `cd desktop && uv run python main.py`, prompt "Đi Đà Lạt 3 ngày, 3 triệu, thích cafe chill".
2. Push `feat/plan-1-core`, mở PR vào `main`.
3. Viết Plan 2 (Revision là vệ tinh ưu tiên #1, không được cắt).
4. Song song: mở rộng `data/places/da-lat.json` lên ~150 Place.

## 2. Luồng hoạt động

### 2.0 Chuẩn bị dữ liệu (ngoài app, chạy một lần)
```
data/places/da-lat.json ──► scripts/import_places.py ──► Postgres (destinations, places)
                               │ kiểm tra tag/kind hợp lệ
                               └ embedding mỗi Place → vector(768)
```
File JSON là nguồn dữ liệu duy nhất; import chạy lại được (upsert theo `ext_id`).

### 2.1 Mở app + đăng nhập
- `desktop/main.py` mở cửa sổ pywebview với `client/dist/index.html` (hoặc `localhost:5173` khi dev).
- Chưa có token → màn Login → `POST /auth/register` hoặc `/auth/login` → bcrypt + JWT 7 ngày → client lưu `localStorage`.
- Có token → màn chính 3 cột: **Chat | Map 3D | Timeline**. Server trả 401 → quay về Login.

### 2.2 Luồng chính: yêu cầu → Itinerary (`server/app/trips.py::_run`)
```
Client streamTrip() — POST /trips (Bearer JWT), đọc SSE
  ├─① "thinking"  "Đang đọc yêu cầu…"
  ├─② agent.parse_trip — LLM lần 1, bắt buộc tool record_trip
  │     → Trip {destination, days, budget, travelers, tags, pace, travel_mode}
  │     (Destination không hỗ trợ / dữ liệu sai → "error", dừng)
  │     → INSERT trips → "trip" {trip_id, center} ⇒ map bay tới thành phố
  ├─③ forecast.get_rain_chance — Open-Meteo (chỉ khi có ngày đi trong 16 ngày; lỗi thì bỏ qua)
  └─④ agent.plan — vòng lặp tool-calling, tối đa 12 lượt
        search_places(query, kind, tags)
          → embed(query) → pgvector: đúng Destination, đủ tag bắt buộc, loại tag cần tránh, top 8
          → "tool_call" {places} ⇒ pin vàng nhấp nháy trên map
        submit_itinerary(draft)
          → rules.build_itinerary:
               • kiểm tra Place đã được search, đủ số ngày, có Stay nếu > 1 ngày
               • Leg: chim bay × 1.3; < 0.8 km đi bộ; chi phí Stop/Stay/xe máy/Grab
               • find_conflicts: vượt Budget, đóng cửa, thiếu tag bắt buộc, mưa + ngoài trời
          → sai: cho LLM làm lại 1 lần
          → có Conflict: cho LLM sửa 1 lần, lần submit thứ 2 được chấp nhận
        → INSERT itineraries (version=1) → "itinerary" {itinerary, places}
```

### 2.3 Nguyên tắc cần giữ khi mở rộng
- **LLM chỉ chọn Place và xếp giờ; tiền và Conflict do code tính** (`server/app/rules.py`).
- **AI chỉ được dùng Place đã có trong kết quả search** (biến `seen` trong `agent.plan`, ADR-0001).
- SSE có 5 event: `thinking`, `trip`, `tool_call`, `itinerary`, `error`. Thêm event mới thì sửa cả server và `AgentEvent` trong `client/src/api.ts`.

### 2.4 Chỗ hổng và điểm nối cho tính năng tiếp theo
| Hiện trạng | Hệ quả / hướng mở rộng |
|---|---|
| Mỗi tin nhắn tạo **Trip mới** | Chưa có Revision. Plan 2: `POST /trips/{id}/revisions` tạo version kế tiếp |
| `version` luôn = 1; DB đã có `UNIQUE(trip_id, version)` | DB sẵn cho lưu nhiều phiên bản và undo |
| Trường `pinned` có trong Stop nhưng chưa dùng | Dùng cho Pinned Stop |
| Server có `GET /trips`, `GET /trips/{id}` nhưng client chưa gọi | Tải lại app mất lịch trình; cần màn "Chuyến đi của tôi" |
| Chi phí Leg theo chim bay × 1.3, map vẽ theo Goong | Số km trên Timeline có thể lệch với đường trên map |
| Mỗi lần search gọi embedding một lần | Chậm, tốn phí; demo_cache ở Plan 5 |
| Chưa có bảng `traveler_profiles` | Plan 2 thêm |
| Dữ liệu 10 Place | AI lặp địa điểm |

## 3. UI/UX hiện tại

Plan 1 chưa có bước thiết kế UI/UX riêng (không mockup, không design system). UI được dựng theo luồng dữ liệu và yêu cầu "map hiện live các bước là khoảnh khắc wow" trong spec.

### 3.1 Luồng màn hình
```
Mở app ──► có token? ──không──► [Login] (một form, nút đổi Đăng nhập/Đăng ký)
              │ có                   │ thành công → lưu token
              ▼                      ▼
        [Màn chính 3 cột] ◄──────────┘
```
Chỉ có 2 màn: không menu, không danh sách chuyến đi, không cài đặt.

### 3.2 Bố cục màn chính
```
┌──────────────┬─────────────────────────────┬────────────────┐
│ CHAT (22rem) │      MAP 3D (co giãn)        │ TIMELINE(24rem)│
│ tiêu đề      │ pin vàng nhấp nháy (search)  │ Tổng chi phí   │
│ gợi ý mẫu    │ pin số theo màu ngày         │ Budget, Chỗ ở  │
│ bong bóng:   │ nhãn "Chỗ ở"                 │ ⚠ Conflict đỏ  │
│ user/ai/     │ tuyến đường màu theo ngày    │ Ngày n · mưa % │
│ tool/error   │                              │ Stop: giờ, giá,│
│ [ô nhập][Gửi]│                              │ lý do          │
└──────────────┴─────────────────────────────┴────────────────┘
```

### 3.3 Trải nghiệm theo event SSE
| Thời điểm | Chat | Map | Timeline |
|---|---|---|---|
| Chưa gõ | Câu gợi ý mẫu | Đà Lạt, nghiêng 45° | "Lịch trình sẽ hiện ở đây." |
| Vừa gửi | Bong bóng user, "AI đang lên lịch trình…", khoá nút Gửi | Xoá pin cũ | — |
| `trip` | — | Bay tới thành phố (zoom 12.5, nghiêng 50°) | Xoá lịch trình cũ |
| `tool_call` | "Đang tìm: … (n kết quả)" | Pin vàng nhấp nháy dồn dần | — |
| `itinerary` | Tóm tắt của AI | Vẽ tuyến Goong theo màu ngày, pin số; camera bay qua từng Stop (~2 giây/Stop) | Tổng tiền, Conflict, từng ngày/Stop |
| `error` | Bong bóng đỏ, lời nhắn tiếng Việt | — | — |

### 3.4 Lựa chọn thiết kế có chủ đích
- **Hiện tiến trình thay vì spinner:** AI chạy 10–30 giây, người xem thấy AI "đang tìm gì".
- **Luôn có Itinerary kèm Conflict** thay vì báo lỗi.
- **Lỗi mạng không chặn demo:** Goong lỗi thì vẽ đường thẳng; stream đứt thì báo trong chat.
- **Tối giản:** tông stone + emerald, Tailwind; `aria-live` cho chat, `role="alert"` cho lỗi đăng nhập.

### 3.5 Điểm yếu UX cần xử lý
1. **Chat chỉ đi một chiều:** mỗi tin nhắn là một chuyến mới (Plan 2 sẽ giải quyết).
2. **Timeline và map không liên kết:** bấm Stop không bay tới Place, bấm pin không hiện gì; chưa có popup hay ảnh Place (dữ liệu đã có `photo_url`).
3. **Không bỏ qua được đoạn camera bay:** 15 Stop mất khoảng 30 giây, người dùng không kéo map được trong lúc đó.
4. **Không có lịch sử chuyến đi:** tải lại app là mất.
5. **Không có đăng xuất;** bố cục 3 cột cố định, cửa sổ tối thiểu 1100 px.
6. **Chưa có nhận diện thương hiệu:** không logo, empty state và màn Login còn trơn, chưa đủ "wow" cho demo.

### 3.6 Hướng tiếp theo cho UI
- **Làm bài bản:** một phiên brainstorm thiết kế riêng để chốt hướng thẩm mỹ, luồng Revision/Pinned, liên kết Timeline ↔ map, màn "Chuyến đi của tôi", rồi dựng mockup để chọn trước khi code.
- **Hoặc sửa nhanh:** xử lý 6 điểm yếu ở mục 3.5 ngay trên bố cục hiện tại.
