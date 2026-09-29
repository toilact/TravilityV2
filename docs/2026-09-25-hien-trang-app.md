# Travility — Hiện trạng app (cập nhật 2026-09-29, sau cá nhân hoá lát 1)

> Ảnh chụp hiện trạng code, dùng làm phụ lục cho [PRD.md](PRD.md). Quyết định và lộ trình nằm trong PRD; tài liệu này chỉ mô tả code **đang chạy thế nào**. Bản đầu viết 2026-09-25 sau Plan 1; bản này thêm lát 1 của [spec cá nhân hoá Trip](superpowers/specs/2026-09-29-ca-nhan-hoa-trip-design.md) (PR #30).

Thuật ngữ in đậm theo [CONTEXT.md](../CONTEXT.md). Spec gốc: [travility-design.md](superpowers/specs/2026-09-25-travility-design.md).

## 1. Tiến độ

- **Plan 1** (nền tảng + AI Trip Planner lõi): ✅ merge `main` (PR #1).
- **Cá nhân hoá lát 1** (PR #30, chờ review): hỏi lại một vòng, giờ đến/về, **Hub**, xe riêng, chat gắn với **Trip** (bản tạm), đủ 3 bữa/ngày, thêm 27 Place.
- **Lát A+B Revision giữ mục đích** (nhánh `feat/revision-giu-muc-dich`): chip Intent + R trên Timeline; "Báo đóng cửa" / "Đổi chỗ khác" trên Stop → tối đa 3 Proposal do code tạo (không LLM) → "Áp dụng" tạo version mới. Chưa có: mưa, trễ giờ, bản đồ theo thời điểm, đánh giá B0/B1/B2, ranker (lát C–F).
- Test: server 128 pass (pytest + Postgres Docker), client 13 pass, build OK.
- **Đã chạy E2E** với Gemini thật qua app desktop (`gemini-3.5-flash-lite`, embedding `gemini-embedding-001`).
- **Dữ liệu:** 37 Place Đà Lạt, trong đó 27 gắn `"unverified": true` chờ kiểm chứng (PRD cần ≥ 150/Destination × 3).
- **Chưa làm:** Revision đầy đủ (chỉ đổi Stop liên quan, Pinned Stop, quay lại version), Traveler Profile, chỗ ở đã đặt, điểm bắt buộc ghé, UI mới, giọng nói, Inspiration Photo, Google login, recap/PDF, demo_cache, đóng gói. Phân công: PRD §12 và GitHub Issues.

## 2. Luồng hoạt động

### 2.0 Chuẩn bị dữ liệu (ngoài app, chạy lại khi sửa JSON)
```
data/places/da-lat.json ──► scripts/import_places.py ──► Postgres (destinations + hubs, places)
                               │ kiểm tra tag/kind/hub hợp lệ
                               └ embedding mỗi Place → vector(768)
```
File JSON là nguồn dữ liệu duy nhất; import upsert theo `ext_id`. `destination.hubs` (tuỳ chọn) khai báo sân bay/bến xe/ga theo **Arrival Mode**.

### 2.1 Mở app + đăng nhập
- `desktop/main.py` mở cửa sổ pywebview với `client/dist/index.html` qua HTTP server nội bộ (cổng 42001), hoặc `localhost:5173` khi dev.
- Chưa có token → màn Login → `POST /auth/register` hoặc `/auth/login` → bcrypt + JWT 7 ngày → client lưu `localStorage`.
- Có token → màn chính 3 cột: **Chat | Map 3D | Timeline**. Server trả 401 → quay về Login.
- Lưu ý: WebKit giữ cache bản build cũ ở `~/Library/Caches/python3` → build client xong mà app trắng thì xoá thư mục đó.

### 2.2 Luồng chính: tin nhắn → Itinerary (`server/app/trips.py`)
```
Client streamTrip(message, tripId) — POST /trips {message, trip_id?} (Bearer JWT), đọc SSE
  ├─ trip_id của User khác → 404 (trước khi mở stream)
  ├─① "thinking"  "Đang đọc yêu cầu…"
  ├─② agent.parse_trip — LLM, bắt buộc tool record_trip, đọc TOÀN BỘ tin nhắn của Trip
  │     → Trip {destination, days, start_date, budget, travelers, tags, pace,
  │             travel_mode?, origin_city?, arrival_mode?, arrival_time?, departure_time?}
  │     trường người dùng không nói = để trống; giờ sai định dạng ("2pm") bị bỏ
  │     tin nhắn tiếp theo: merge_trip giữ câu trả lời cũ, trống thì mặc định (xe-may)
  │     → INSERT/UPDATE trips (spec, user_messages) → "trip" {trip_id, trip, center}
  ├─③ Trip mới + missing_questions() khác rỗng?
  │     → "clarify" {trip_id, questions} rồi ĐÓNG stream          (hỏi tối đa 1 vòng)
  │       câu hỏi: travel_mode (nếu chưa nói); arrival (nếu có ngày đi mà chưa biết giờ)
  │       client: POST /trips/{id}/plan {travel_mode?, arrival_*?}  ({} = "Bỏ qua")
  │         → apply_answers bằng code (không gọi LLM) → 404/409/422 trước khi stream
  │         → "trip" rồi tiếp tục ④⑤
  ├─④ forecast.get_rain_chance — Open-Meteo (chỉ khi có ngày đi trong 16 ngày; lỗi thì bỏ qua)
  └─⑤ agent.plan — vòng lặp tool-calling, tối đa 12 lượt
        brief: Trip + giờ đến/về + Hub + khả năng mưa + NGUYÊN VĂN tin nhắn người dùng
        search_places(query, kind, tags)
          → embed(query) → pgvector: đúng Destination, đủ tag bắt buộc, loại tag cần tránh, top 8
          → "tool_call" {places} ⇒ pin vàng nhấp nháy trên map
        submit_itinerary(draft)
          → rules.build_itinerary:
               • kiểm tra Place đã được search, đủ số ngày, có Stay nếu > 1 ngày
               • route mỗi ngày: [Hub ngày 1 | Stay] → Stop… → [Hub ngày cuối | Stay]
               • Leg: chim bay × 1.3; < 0.8 km đi bộ; xe máy thuê / riêng, ô tô riêng, Grab
               • find_conflicts: vượt Budget, đóng cửa, thiếu tag, mưa + ngoài trời,
                 before_arrival, after_departure, missing_meal
          → sai: cho LLM làm lại 1 lần
          → có Conflict: gửi lại cho LLM sửa 1 lần, lần submit thứ 2 được chấp nhận
        → INSERT itineraries (version = max + 1) → "itinerary" {itinerary, places, trip_id, version}
```

Sự cố trên một Stop (`server/app/proposals.py`, JSON thường, không SSE):
```
POST /trips/{id}/disruptions {version, kind: closed|disliked, day_index, stop_index}
  → version khác bản mới nhất: 409 · Stop đã ghim / không tồn tại: 422 · Trip của User khác: 404
  → replan.propose: ứng viên = similar_places (embedding đã lưu, cùng kind, bỏ Place đã dùng + Tag tránh)
      → lọc is_open + kịp giờ (make_leg) → xếp theo score(features) → build_itinerary
      → loại phương án sinh Conflict cứng mới → tối đa 3 Proposal + metrics + reason_codes + câu giải thích
  → INSERT proposals (kiêm log feedback) → {proposal_id, options} hoặc {proposal_id, no_feasible}
POST /trips/{id}/proposals/{pid}/apply {option}
  → khoá dòng proposals; đã áp dụng cùng option → trả version cũ (idempotent), option khác → 409
  → save_itinerary (version = max + 1), lưu chosen_index → "itinerary" {…, version}
```

### 2.3 Nguyên tắc cần giữ khi mở rộng
- **LLM chỉ chọn Place và xếp giờ; tiền và Conflict do code tính** (`server/app/rules.py`).
- **AI chỉ được dùng Place đã có trong kết quả search** (biến `seen` trong `agent.plan`, ADR-0001).
- **Code quyết định có hỏi lại hay không** (`missing_questions`), không phải LLM; câu trả lời chip áp bằng code (`apply_answers`).
- SSE có 6 event: `thinking`, `trip`, `tool_call`, `clarify`, `itinerary`, `error`. Thêm event mới thì sửa cả server và `AgentEvent` trong `client/src/api.ts`.
- Agent gửi lại nguyên message của LLM (`model_dump`) — Gemini 3 cần `thought_signature` trong tool_calls.
- Khung giờ bữa ăn (`MEALS`) có ở cả `rules.py` và `client/src/api.ts` — đổi thì đổi cả hai.
- **Proposal do code tạo, không gọi LLM** (ADR-0006). Bảng `INTENT_LABELS` có ở cả `domain.py` và `client/src/api.ts` — đổi thì đổi cả hai.

### 2.4 Chỗ hổng và điểm nối cho tính năng tiếp theo
| Hiện trạng | Hệ quả / hướng mở rộng |
|---|---|
| Tin nhắn tiếp theo **lập lại toàn bộ** lịch trình | Revision đầy đủ (#22): chỉ đổi Stop liên quan |
| Có nhiều version nhưng UI chỉ hiện bản mới nhất | "Quay lại bản này" (#24) |
| Trường `pinned` có trong Stop nhưng chưa dùng | Pinned Stop (#25) |
| `user_messages` lưu trong `trips`; client chưa gọi `GET /trips` | Tải lại app mất lịch trình; lịch sử chat + danh sách Trip (#17, #3) |
| AI có thể xếp Place `cho-o` làm Stop → tiền phòng tính 2 lần | Từ chối trong `_check_draft` |
| Kem/ăn vặt (kind `an-uong`) vẫn tính là bữa chính | Tag `an-vat` không tính là bữa |
| Vượt Budget chỉ báo một dòng, không có bảng chi phí | Gửi breakdown cho AI + hiện trên Timeline |
| Leg Hub → thành phố tính theo Travel Mode | Tính theo Arrival Mode |
| Chi phí Leg theo chim bay × 1.3, map vẽ theo Goong | Goong Distance Matrix (#7) |
| Mỗi lần search gọi embedding một lần; Gemini free giới hạn request/phút | demo_cache (#14); demo nên dùng OpenAI |
| Chưa có Traveler Profile, chỗ ở đã đặt, điểm bắt buộc ghé | Lát 2–3 của spec cá nhân hoá (#18) |
| Dữ liệu 37 Place, 27 chưa kiểm chứng | #19 |

## 3. UI/UX hiện tại

Chưa có bước thiết kế UI/UX riêng (mockup: #2). UI dựng theo luồng dữ liệu và yêu cầu "map hiện live các bước là khoảnh khắc wow".

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
│ tiêu đề +    │ pin vàng nhấp nháy (search)  │ Tổng chi phí   │
│ [＋Chuyến mới]│ pin số theo màu ngày         │ Budget, Chỗ ở  │
│ bong bóng:   │ nhãn "Chỗ ở"                 │ ⚠ Conflict đỏ  │
│ user/ai/     │ tuyến đường màu theo ngày    │ Ngày n · mưa % │
│ tool/error   │ (Leg tới/từ Hub chưa vẽ)     │ Stop: 🍜 bữa,  │
│ thẻ hỏi lại  │                              │ giờ, giá, lý do│
│ [ô nhập][Gửi]│                              │                │
└──────────────┴─────────────────────────────┴────────────────┘
```

### 3.3 Trải nghiệm theo event SSE
| Thời điểm | Chat | Map | Timeline |
|---|---|---|---|
| Chưa gõ | Câu gợi ý mẫu | Đà Lạt, nghiêng 45° | "Lịch trình sẽ hiện ở đây." |
| Vừa gửi | Bong bóng user, "AI đang lên lịch trình…", khoá nút Gửi | Xoá pin cũ | — |
| `trip` | Nhớ `tripId` → tin sau thuộc Trip này; hiện nút "Chuyến mới" | Bay tới thành phố | Xoá lịch trình cũ |
| `clarify` | Thẻ hỏi lại: chip phương tiện, chip phương tiện đến + ô giờ tới/về, "Lên lịch" / "Bỏ qua, cứ lên lịch". Gõ tay vào ô chat cũng được | — | — |
| `tool_call` | "Đang tìm: … (n kết quả)" | Pin vàng nhấp nháy dồn dần | — |
| `itinerary` | Tóm tắt của AI; thẻ hỏi lại biến mất | Vẽ tuyến Goong theo màu ngày, pin số; camera bay qua từng Stop | Tổng tiền, Conflict, từng ngày/Stop, nhãn Bữa sáng/trưa/tối |
| `error` | Bong bóng đỏ, lời nhắn tiếng Việt; thẻ hỏi lại **vẫn giữ** để sửa/thử lại | — | — |
| "＋ Chuyến mới" | Xoá chat, thẻ hỏi lại, `tripId` | Xoá pin | Xoá lịch trình |
| "Báo đóng cửa" / "Đổi chỗ khác" trên Stop (khoá khi Stop đã ghim) | Lỗi 409/422 hiện bong bóng đỏ | Pin vàng tại Place thay thế | Panel "Phương án thay thế": ≤ 3 thẻ, câu giải thích, Δ chi phí / Δ phút / R; hoặc lý do không có phương án |
| "Áp dụng" | "Đã áp dụng phương án — lịch trình bản N." | Xoá pin vàng, vẽ lại tuyến | Lịch trình bản mới, panel đóng |

### 3.4 Lựa chọn thiết kế có chủ đích
- **Hiện tiến trình thay vì spinner:** AI chạy 10–30 giây, người xem thấy AI "đang tìm gì".
- **Luôn có Itinerary kèm Conflict** thay vì báo lỗi.
- **Hỏi lại tối đa một vòng, luôn bỏ qua được** — không chặn người dùng bằng form.
- **Lỗi mạng không chặn demo:** Goong lỗi thì vẽ đường thẳng; stream đứt thì báo trong chat.
- **Tối giản:** tông stone + emerald, Tailwind; `aria-live` cho chat, `aria-pressed` cho chip, `role="alert"` cho lỗi đăng nhập.

### 3.5 Điểm yếu UX cần xử lý
1. **Chưa xem/khôi phục được version cũ;** mỗi tin nhắn lập lại cả lịch trình (#22, #24).
2. **Timeline và map không liên kết:** bấm Stop không bay tới Place, bấm pin không hiện gì; chưa có popup hay ảnh Place (#4).
3. **Không bỏ qua được đoạn camera bay;** người dùng không kéo map được trong lúc đó.
4. **Không có lịch sử chuyến đi / đăng xuất:** tải lại app là mất (#3, #17).
5. **Bố cục 3 cột cố định,** cửa sổ tối thiểu 1100 px; chưa có logo, empty state trơn (#2, #16).
6. **Không thấy tiền đi đâu:** Timeline chỉ có tổng và từng Stop, chưa có bảng chi phí theo nhóm.
