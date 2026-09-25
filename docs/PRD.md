# Travility — PRD (Product Requirements Document)

> Phiên bản 1 · 2026-09-25 · Người đọc: toàn bộ thành viên nhóm.
> PRD là nguồn chính trả lời **làm gì và vì sao**. Chi tiết kỹ thuật từng giai đoạn nằm trong [docs/superpowers/plans/](superpowers/plans/).
> Thuật ngữ in đậm theo [CONTEXT.md](../CONTEXT.md). Quyết định kiến trúc ở [docs/adr/](adr/). Hiện trạng code chi tiết: [2026-09-25-hien-trang-app.md](2026-09-25-hien-trang-app.md).

Ký hiệu trạng thái: ✅ đã có trong code (nhánh `feat/plan-1-core`) · 🟡 có một phần · ⏳ chưa làm.

---

## 1. Tổng quan & vấn đề

Người Việt đi du lịch trong nước thường mất hàng giờ ghép thông tin từ nhiều nguồn: chọn điểm tham quan, quán ăn, chỗ ở, tính đường đi và tổng chi phí sao cho vừa ngân sách. Kết quả thường là một lịch trình đi vòng, vượt ngân sách, hoặc ghé nơi đang đóng cửa.

**Travility** là app desktop: người dùng mô tả chuyến đi bằng một câu ("Đi Đà Lạt 3 ngày, 3 triệu, thích cafe chill"), AI dựng **Itinerary** theo ngày trên bản đồ 3D, dùng **Place** thật đã được kiểm chứng. Chi phí và các **Conflict** (vượt Budget, đóng cửa, mưa…) do code tính chính xác. Sau đó người dùng chỉnh lịch trình bằng hội thoại (**Revision**).

Bối cảnh: đồ án nhóm 4 người, 10 tuần, demo trực tiếp 10–15 phút trên một laptop trước giảng viên.

## 2. Mục tiêu & chỉ số thành công

**Mục tiêu chính:** kịch bản demo (mục 3.2) chạy trơn tru từ đầu đến cuối trên laptop demo, kể cả khi mất mạng.

| Chỉ số | Mục tiêu | Cách đo |
|---|---|---|
| Itinerary hợp lệ (không Place lạ, đúng số ngày, có Stay) | ≥ 90% | Golden set 15 prompt × 2 provider (Gemini dev, OpenAI demo) |
| Thời gian từ gửi yêu cầu đến có Itinerary | < 30 giây (OpenAI) | Đo trong golden set |
| Sự kiện đầu tiên hiện trên UI | < 2 giây | Event `thinking` ngay khi gửi |
| Revision chỉ đổi Stop liên quan, không đụng Pinned Stop | 100% | pytest + golden set Revision |
| Dữ liệu Place | Đà Lạt ≥ 150 (T4); 2 Destination còn lại ≥ 150 mỗi nơi (T8) | Đếm trong `data/places/` |
| Demo offline | Chạy hết kịch bản khi tắt mạng | Diễn tập với demo_cache |

**Không phải mục tiêu:** phát hành cho người dùng thật, chạy nhiều máy, doanh thu.

## 3. Người dùng & kịch bản

### 3.1 Người dùng
- **Người lên kế hoạch cho nhóm nhỏ** (1–10 người): sinh viên, nhân viên văn phòng, gia đình. Họ biết mình thích gì ("cafe chill", "ăn chay", "thiên nhiên") và có ngân sách, nhưng không muốn tự ghép lịch.
- **Người xem demo (giảng viên):** cần thấy rõ AI "đang làm gì", kết quả đáng tin (Place thật, tiền tính đúng) và có khoảnh khắc "wow".

### 3.2 Kịch bản demo (10–15 phút)
1. Mở app → đăng nhập (hoặc đăng ký → onboarding chọn sở thích).
2. Gõ hoặc nói: "Đi Đà Lạt 3 ngày, 2 người, 3 triệu, thích cafe chill và thiên nhiên".
3. Map bay tới Đà Lạt. Pin vàng nhấp nháy xuất hiện dần theo từng lần AI tìm Place (**khoảnh khắc wow chính**).
4. Itinerary hiện ra: tuyến đường tô màu theo ngày, Timeline có giờ, giá, lý do chọn, tổng chi phí so với Budget, Conflict (nếu có).
5. Bấm "Xem hành trình": camera bay qua từng Stop.
6. Ghim một quán cafe → nói "Ngày 2 mưa thì sao?" → chỉ các Stop ngoài trời đổi; Stop đã ghim giữ nguyên; map animate chỗ đổi; version v2 xuất hiện.
7. "Bớt 500k" → v3 rẻ hơn. Bấm v1 để xem lại, "Quay lại bản này".
8. "Đổi sang homestay" → Stay đổi, chi phí tính lại.
9. Thả một ảnh cảm hứng → 3–5 Suggestion hiện trên map → chấp nhận một cái.
10. Cinematic recap có thuyết minh → xuất PDF.
11. Tắt wifi, chạy lại bước 2 → vẫn chạy nhờ demo_cache.

## 4. Thuật ngữ

Dùng đúng thuật ngữ trong [CONTEXT.md](../CONTEXT.md): User, Traveler Profile, Destination, Trip, Itinerary, Conflict, Revision, Pinned Stop, Place, Stop, Suggestion, Inspiration Photo, Stay, Leg, Travel Mode, Pace, Forecast, Tag, Preference. Tránh các từ trong mục _Avoid_ của file đó, cả trong code lẫn UI.

## 5. Yêu cầu chức năng

### 5.1 Tài khoản
| Yêu cầu | Trạng thái |
|---|---|
| Đăng ký / đăng nhập email + mật khẩu (bcrypt, JWT 7 ngày) | ✅ |
| Mỗi User chỉ thấy Trip của mình | ✅ |
| Đăng xuất | ⏳ |
| Đăng nhập Google (loopback redirect cho app desktop) | ⏳ (cắt đầu tiên nếu trễ) |
| Quên mật khẩu qua email | ⏳ (cắt đầu tiên nếu trễ) |

Tiêu chí chấp nhận: token hết hạn → về màn đăng nhập kèm thông báo; User A gọi `GET /trips/{id}` của User B → 404.

### 5.2 Traveler Profile ⏳
- Sau khi đăng ký: **onboarding 1 màn**, bỏ qua được. Chọn Tag sở thích bằng chip có icon (bắt buộc / ưu tiên / tránh), Pace, Travel Mode.
- Sửa trong màn **Hồ sơ**.
- Khi tạo Trip, Profile được chép vào Trip. **Câu chat luôn thắng Profile** khi mâu thuẫn. Đổi Profile không ảnh hưởng Trip đã có.
- Cần bảng `traveler_profiles`.
- Nếu trễ: cắt onboarding, giữ màn Hồ sơ.

### 5.3 Lập Trip & Itinerary (lõi)
| Yêu cầu | Trạng thái |
|---|---|
| Hiểu câu tự nhiên → Trip (Destination, số ngày, ngày đi, số người, Budget, Tag, Pace, Travel Mode) | ✅ |
| Destination chưa hỗ trợ → báo rõ danh sách đang có | ✅ |
| AI tìm Place bằng pgvector (đúng Destination, đủ Tag bắt buộc, loại Tag cần tránh) | ✅ |
| AI chỉ được dùng Place đã trả về từ tool; Place lạ → làm lại 1 lần (ADR-0001) | ✅ |
| Stream tiến trình qua SSE (`thinking`, `trip`, `tool_call`, `itinerary`, `error`) | ✅ |
| Luôn trả Itinerary kèm Conflict thay vì báo lỗi | ✅ |
| Mỗi Stop có lý do chọn (reason) | ✅ |
| Lưu Trip + Itinerary; mở lại Trip cũ | 🟡 server có API, client chưa dùng |
| Trả lời bằng giọng nói / nhập bằng giọng nói | ⏳ (mục 5.8) |

Tiêu chí chấp nhận: 15 prompt golden set cho ≥ 90% Itinerary hợp lệ; không bao giờ xuất hiện Place không có trong database.

### 5.4 Revision, Pinned Stop, phiên bản ⏳ (không được cắt)
- **Chat gắn với Trip đang mở.** Khi đã có Itinerary, mọi tin nhắn là một Revision của Trip đó. Muốn chuyến khác thì bấm nút **"Chuyến mới"**. App không tự đoán ý người dùng.
- Mỗi Trip có lịch sử chat riêng, được lưu lại (mở Trip cũ thấy lại hội thoại).
- Mỗi Revision tạo **một version Itinerary mới, bất biến**. Chỉ Stop liên quan đến yêu cầu được đổi.
- **Pinned Stop:** ghim / bỏ ghim từ popup Place hoặc icon trên Timeline. Ghim **không tạo version mới**; đây là trạng thái áp cho Revision kế tiếp. Code kiểm tra Draft và **từ chối Draft đổi hoặc xoá Stop đã ghim** (AI làm lại 1 lần, giống cơ chế Place lạ).
- **Version:** Timeline có dãy `v1 · v2 · v3`. Bấm version cũ để xem. "Quay lại bản này" tạo version mới chép từ bản cũ, không xoá gì.
- Sau Revision: Stop thay đổi được tô sáng trên Timeline và animate trên map (client so sánh hai version).

Tiêu chí chấp nhận: pytest chứng minh Draft đụng Pinned Stop bị từ chối; Revision "bớt 500k" cho version mới có `total_cost` thấp hơn; undo không làm mất version nào.

### 5.5 Chỗ ở (Stay)
| Yêu cầu | Trạng thái |
|---|---|
| Một Stay cho cả Trip (bắt buộc khi Trip > 1 ngày), là điểm đầu/cuối mỗi ngày | ✅ |
| Tính theo đêm × số phòng (2 người/phòng) | ✅ |
| Phân loại chỗ ở bằng Tag: `khach-san`, `homestay`, `hostel`, `resort` | ⏳ thêm vào bộ Tag và dữ liệu |
| Đổi Stay bằng Revision ("đổi sang homestay rẻ hơn") | ⏳ đi cùng 5.4 |

### 5.6 Đường đi & chi phí
| Yêu cầu | Trạng thái |
|---|---|
| Leg giữa các điểm liên tiếp; Leg < ~800 m thì đi bộ | ✅ |
| Chi phí: xe máy thuê theo ngày × số xe + xăng/km; Grab theo công thức cố định | ✅ |
| Budget = ăn + vé + Stay + Leg (không gồm di chuyển liên tỉnh, ADR-0005) | ✅ |
| Km thật từ **Goong Distance Matrix ở server**; lỗi thì dùng chim bay × 1.3 | ⏳ hiện chỉ có chim bay × 1.3 |
| Conflict mới **"không kịp di chuyển"**: thời gian Leg dài hơn khoảng trống giữa hai Stop | ⏳ |
| Tối ưu thứ tự Stop bằng thuật toán | ❌ ngoài phạm vi (phá khung giờ AI đã xếp) |

Tiêu chí chấp nhận: km trên Timeline khớp với tuyến Goong vẽ trên map (sai số < 10%).

### 5.7 Forecast ✅
- Trip có ngày đi trong 16 ngày tới → lấy khả năng mưa theo ngày từ Open-Meteo. Lỗi thì lập lịch không có thời tiết.
- Ngày mưa ≥ 60% + Stop ngoài trời → Conflict `rain_outdoor`.

### 5.8 Giọng nói ⏳
- Nút mic → STT (OpenAI) → gửi như tin nhắn chat.
- Câu tóm tắt của AI được đọc bằng TTS (OpenAI); có nút tắt tiếng.

### 5.9 Inspiration Photo ⏳ (cắt thứ 3 nếu trễ)
- Kéo thả ảnh → vision mô tả không khí → embedding → 3–5 **Suggestion** hiện trên map với màu riêng.
- Chấp nhận một Suggestion = một Revision ("thêm nơi này vào ngày 2").

### 5.10 Cinematic recap + PDF ⏳ (recap cắt thứ 2 nếu trễ)
- Nút "Xem hành trình" (bản đơn giản, làm cùng UI mới): camera bay qua các Stop, dừng được bất cứ lúc nào.
- Recap đầy đủ: bay toàn tuyến kèm thuyết minh TTS.
- Xuất PDF: Itinerary theo ngày + bảng chi phí. Đây là cách chia sẻ Trip duy nhất.

## 6. Quy tắc nghiệp vụ

Code thực thi, không để prompt quyết định. Nguồn: spec + các quyết định mới.

- AI chỉ tham chiếu Place trả về từ tool. Place lạ bị từ chối, AI làm lại 1 lần (ADR-0001).
- **LLM chỉ chọn Place và xếp giờ; tiền, Leg và Conflict do code tính** (`server/app/rules.py`).
- Budget = ăn + vé + Stay + chi phí Leg; không gồm di chuyển liên tỉnh.
- Một Stay cho cả Trip (bắt buộc khi Trip > 1 ngày); đêm × số phòng (2 người/phòng); không phải Stop.
- Chi phí Stop = giá Place × số người. Xe máy thuê = ngày × số xe (2 người/xe).
- Pace: thong thả 3–4 Stop (9h–20h) · vừa 5 (8h–21h) · dày 6–7 (7h–22h).
- Conflict: vượt Budget · ngoài giờ mở cửa (theo thứ nếu có ngày đi) · thiếu Tag bắt buộc · Stop ngoài trời ngày mưa ≥ 60% · *(mới)* không kịp di chuyển giữa hai Stop.
- Revision không được sửa hay xoá Pinned Stop. Ghim không tạo version.
- Itinerary bất biến. Mọi thay đổi (kể cả "quay lại bản cũ") tạo version mới.
- Câu chat thắng Traveler Profile khi mâu thuẫn.
- Trip: 1–7 ngày, 1–10 người, Budget > 0, đúng một Destination.

## 7. UI/UX

### 7.1 Luồng màn hình
```
Mở app ─► có token? ─không─► [Đăng nhập / Đăng ký] ─(đăng ký)─► [Onboarding sở thích] (bỏ qua được)
             │ có                      │                                   │
             ▼                         ▼                                   ▼
       [Màn chính] ◄───────────────────┴───────────────────────────────────┘
       mở Trip gần nhất (hoặc empty state nếu chưa có)
```

### 7.2 Bố cục màn chính (thay 3 cột cố định hiện tại)
```
┌──┬──────────────────────────────────────────────────────────┐
│R │                 BẢN ĐỒ 3D TOÀN MÀN HÌNH                  │
│A │  ┌───────────┐                          ┌─────────────┐  │
│I │  │ CHAT      │                          │ TIMELINE    │  │
│L │  │ panel nổi │     pin, tuyến, popup    │ panel nổi   │  │
│  │  │ thu gọn   │                          │ v1·v2·v3    │  │
│  │  │ được      │                          │ chi phí,    │  │
│  │  │ [🎤][ô][➤]│   [▶ Xem hành trình]     │ Conflict    │  │
│  │  └───────────┘                          └─────────────┘  │
└──┴──────────────────────────────────────────────────────────┘
Rail: ＋ Chuyến mới · 🗂 Danh sách Trip (ngăn kéo) · 👤 Hồ sơ · ⎋ Đăng xuất
```

### 7.3 Hành vi theo sự kiện
| Thời điểm | Chat | Map | Timeline |
|---|---|---|---|
| Chưa có Trip | Empty state có ảnh + câu gợi ý bấm được | Destination mặc định | Ẩn / thu gọn |
| Vừa gửi | Bong bóng user; trạng thái "AI đang lên lịch…"; khoá gửi | Xoá pin tìm kiếm cũ | — |
| `trip` | — | Bay tới thành phố | Xoá lịch trình cũ |
| `tool_call` | "Đang tìm: … (n kết quả)" | Pin vàng nhấp nháy dồn dần | — |
| `itinerary` (lần đầu) | Tóm tắt của AI (+ TTS) | Vẽ tuyến theo màu ngày; **fit toàn tuyến** (không tự bay) | Tổng tiền, Conflict, các ngày |
| `itinerary` (Revision) | Tóm tắt thay đổi | Animate Stop đổi | Version mới trong dãy; tô sáng Stop đổi |
| `error` | Bong bóng đỏ, lời nhắn tiếng Việt | — | — |

### 7.4 Tương tác
- **Map ↔ Timeline hai chiều.** Bấm Stop trên Timeline → map bay tới Place + mở popup. Bấm pin → Timeline cuộn tới Stop đó.
- **Popup Place:** ảnh, tên, giá, giờ mở hôm đó, trong nhà/ngoài trời, nút **Ghim**.
- **"Xem hành trình":** camera bay qua từng Stop, dừng được. Người dùng luôn có thể kéo map.
- **Danh sách Trip:** Destination, số ngày, ngày tạo. Bấm để mở Trip kèm lịch sử chat và version mới nhất.

### 7.5 Nguyên tắc thẩm mỹ
- Bản đồ là nhân vật chính, chiếm trọn màn hình. Chat và Timeline là panel nổi bán trong suốt, thu gọn được.
- Tông ấm gợi du lịch Việt; có logo; empty state có ảnh; thẻ Stop có ảnh Place.
- Luôn hiện tiến trình thay vì spinner trống. Lỗi hiện bằng câu tiếng Việt thân thiện, không chặn thao tác.
- Mockup chi tiết chốt trong một phiên thiết kế riêng trước khi code UI mới.

## 8. Kiến trúc

Chi tiết: [ADR-0002](adr/0002-postgres-tu-host-app-desktop-la-client.md), [ADR-0003](adr/0003-mot-sdk-openai-hai-provider.md), [ADR-0004](adr/0004-goong-cho-ban-do.md).

```
CLIENT (desktop/ + client/)          pywebview + React/Vite/Tailwind + MapLibre (tile/Directions Goong)
   │ HTTP + SSE, JWT                  chỉ lưu JWT
SERVER (docker compose)
   api  FastAPI: auth · agent · tools · rules · forecast · (voice · vision · demo_cache)
        giữ key LLM/embedding; gọi OpenAI/Gemini, Open-Meteo, Goong Distance Matrix (mới)
   db   Postgres + pgvector: users, traveler_profiles*, destinations, places, trips,
        itineraries (version), messages*        (* = bảng mới)
```
- Server tắt thì app không dùng được. Khi demo, cả hai chạy trên một laptop; cổng chỉ mở trên `127.0.0.1`.
- **API mới dự kiến:** `POST /trips/{id}/revisions` (SSE, trả version mới) · `POST /trips/{id}/restore/{version}` · `PATCH /trips/{id}/pins` · `GET/PUT /profile` · `GET /trips/{id}/messages`.
- **Event SSE:** giữ 5 event hiện có. Event `itinerary` thêm `version` và danh sách Stop đã đổi. Thêm event mới thì phải sửa cả server lẫn kiểu `AgentEvent` trong `client/src/api.ts`.

## 9. Dữ liệu Place

- Nguồn duy nhất: `data/places/<destination>.json`, commit vào git. Nạp bằng `scripts/import_places.py` (upsert, sinh embedding). Không có màn Admin; sửa Place = sửa JSON + PR + chạy lại import.
- Trường: `ext_id`, tên, `kind` (an-uong, cafe, tham-quan, giai-tri, cho-o), toạ độ, giá, giờ mở theo thứ, trong nhà/ngoài trời, Tag (bộ từ vựng cố định), mô tả, ảnh.
- **Quy trình bán tự động:**
  1. Lấy ứng viên (tên, toạ độ, loại) từ OpenStreetMap/Goong.
  2. AI nháp Tag, mô tả, giá.
  3. **Thành viên kiểm chứng tay** (Place phải có thật và đúng).
  4. Commit JSON.
- Mục tiêu: Đà Lạt ≥ 150 (hiện 10) trước T4; Đà Nẵng – Hội An và Hà Nội ≥ 150 mỗi nơi trước T8.
- Ảnh Place lưu local phía server để demo không phụ thuộc mạng.

## 10. Yêu cầu phi chức năng
- **Hiệu năng:** event đầu < 2 s; Itinerary < 30 s với OpenAI.
- **Chịu lỗi:** Goong lỗi → vẽ đường thẳng / dùng km chim bay; Forecast lỗi → bỏ qua; LLM lỗi → thông báo thử lại; stream đứt → báo trong chat.
- **Demo offline:** demo_cache ghi và phát lại phản hồi theo hash(request).
- **Bảo mật:** mọi secret nằm trong `.env`, không commit. Key Goong nằm trong bundle client, chấp nhận cho demo; nếu phát hành phải giới hạn domain hoặc cho server làm proxy.
- **Tiếng Việt:** toàn bộ UI và câu trả lời AI bằng tiếng Việt.
- **Đóng gói:** PyInstaller cho client desktop; server bằng `docker compose`.

## 11. Ngoài phạm vi
- Phát hành cho người dùng thật, hosting, nhiều máy dùng chung server.
- Nhiều Stay trong một Trip; đặt phòng / thanh toán.
- Chia sẻ Trip trong app (chỉ xuất PDF).
- Thuật toán tối ưu thứ tự Stop.
- Di chuyển liên tỉnh (vé máy bay, xe khách).
- Màn Admin quản lý Place.

## 12. Lộ trình & phân vai

Bắt đầu 2026-09-25. Công việc được theo dõi bằng GitHub Issues #2–#29.

| Thành viên | Vai | Issue |
|---|---|---|
| **Đỗ Chí Thành** (@toilact) — trưởng nhóm | B: Agent, rules, Revision (đường găng) + Goong Matrix + golden set + demo | #17, #22, #24, #25, #26, #18, #7, #27, #6, #29 |
| **Nguyễn Thanh Tùng** (@nguyentung206) | A: Client React, bản đồ, UI mới, giọng nói phía client, recap | #2, #3, #4, #16, #23, #8, #9, #28 |
| **Đặng Trần Minh Nhật** (@MinhATT) | D: Inspiration Photo, PDF, Google login, quên mật khẩu, demo_cache, đóng gói | #10, #11, #12, #13, #14, #15 |
| **Nguyễn Duy Quân** (@skyduyquan2-sudo) | C: Dữ liệu Place (script thu thập + 3 Destination) | #5, #19, #20, #21 |

| Tuần | Nội dung | Trạng thái |
|---|---|---|
| T1 | Plan 1: nền tảng + AI Trip Planner lõi | ✅ |
| T2–3 | Plan 2: Revision + Pinned + version + Traveler Profile; UI mới (map full, panel nổi, rail, Map↔Timeline) | ⏳ |
| T4 | Đà Lạt 150 Place; Goong Distance Matrix + Conflict "không kịp" | ⏳ |
| T5 | Giọng nói (STT/TTS) | ⏳ |
| T6 | Inspiration Photo → Suggestion | ⏳ |
| T7 | Google login + quên mật khẩu | ⏳ |
| T8 | Recap + PDF; 2 Destination còn lại | ⏳ |
| T9 | Chuyển sang OpenAI, golden set, polish | ⏳ |
| T10 | demo_cache, PyInstaller, kịch bản và diễn tập demo | ⏳ |

## 13. Thứ tự cắt khi trễ
1. Google login + quên mật khẩu
2. Cinematic recap (giữ nút "Xem hành trình" đơn giản)
3. Inspiration Photo
4. Onboarding (giữ màn Hồ sơ)
5. Destination thứ 3

**Không cắt:** lõi lập Itinerary · Revision + Pinned + version · email/mật khẩu · UI mới · Đà Lạt 150 Place.

## 14. Rủi ro
| Rủi ro | Xử lý |
|---|---|
| Gemini và OpenAI khác nhau về tool-calling | Golden set 15 prompt chạy trên cả hai; 2 tuần cuối chỉ dùng OpenAI |
| Thiếu dữ liệu → AI lặp Place, demo kém | Quy trình bán tự động; Đà Lạt ưu tiên số 1 |
| Server phải chạy khi demo | `docker compose up` trên laptop demo; checklist khởi động |
| Mạng yếu khi demo | demo_cache replay; ảnh Place lưu local |
| Làm lại UI tốn thời gian | Chốt mockup trước; giữ nguyên logic SSE hiện có |
| Revision đổi quá nhiều Stop | Kiểm tra bằng code + golden set Revision |
| Goong Matrix hết quota / lỗi | Fallback công thức chim bay × 1.3 |

## 15. Câu hỏi mở
- Có cần ADR cho việc chuyển tính km sang Goong Distance Matrix ở server không?
- Nguồn ảnh Place (tự chụp, Goong, Wikimedia) và vấn đề bản quyền.
- Giới hạn độ dài lịch sử chat gửi cho LLM trong mỗi Revision.
- Có vẽ lại tuyến đường trên map bằng dữ liệu từ server để khỏi gọi Goong Directions ở client không?
