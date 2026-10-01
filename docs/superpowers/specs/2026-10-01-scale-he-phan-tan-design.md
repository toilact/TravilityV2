# Scale Travility thành hệ phân tán + mô hình dự đoán mưa

> 2026-10-01 · T2–T7 trong [ROADMAP](../../ROADMAP.md) · Người làm: Thành · [ADR-0007](../../adr/0007-cum-phan-tan-tren-docker-compose.md), [ADR-0008](../../adr/0008-cap-theo-loai-du-lieu.md).
> Thuật ngữ theo [CONTEXT.md](../../../CONTEXT.md).

## 1. Mục tiêu

Giảng viên chấm cao khi đồ án có nhiều AI và áp dụng: load balancing, caching, sharding, message queue, replication, distributed system, microservice, rate limit, CAP. Lát này biến server một tiến trình thành một cụm chạy bằng docker compose trên laptop demo, trong đó:

1. Mỗi kỹ thuật giải một vấn đề có thật của Travility (§3), không gắn vào cho có.
2. Mỗi kỹ thuật **trình diễn được** trong buổi demo: có số liệu load test, và tắt một node thì thấy hệ thống phản ứng (§12).
3. Client và việc của Nhật, Tùng, Quân không bị ảnh hưởng: hợp đồng HTTP + SSE giữ nguyên.
4. Luôn còn đường lui: `docker compose up` như hiện nay vẫn chạy được toàn bộ app.

Thêm một mô hình tự huấn luyện: dự đoán khả năng mưa cho ngày đi xa hơn 16 ngày, kèm giải thích (§11).

Không làm: triển khai cloud, tự động chuyển node chính (failover), thêm shard khi đang chạy, cache theo ngữ nghĩa, dự đoán động đất, dự đoán độ đông, cá nhân hoá / recommender.

## 2. Quyết định (chốt trong buổi brainstorm 2026-10-01)

| # | Quyết định | Lý do |
|---|---|---|
| S1 | Chấm bằng demo chạy thật trên laptop, không cloud | Không tốn tiền, không phụ thuộc mạng, khớp yêu cầu demo offline |
| S2 | Hạ tầng T2–T6, đóng băng kiến trúc cuối T6; mô hình mưa T7; #37 + #26 ở T8 | Dùng 3 tuần đang dư; còn 4 tuần ổn định trước demo |
| S3 | 4 service tách theo loại tải: `api`, `planner`, `llm-gateway`, `places` | Mỗi service có lý do tồn tại riêng; 7–8 service thì 5 tuần chỉ đủ nối dây |
| S4 | Một codebase, một image Docker, mỗi service là một lệnh khởi động khác nhau | Giữ 203 test và các hàm dùng chung (`rules`, `domain`); service vẫn là tiến trình và container riêng, nói chuyện qua HTTP / queue |
| S5 | Redis Streams cho queue; cùng Redis cho cache và rate limit | Ít thành phần nhất; consumer group có xác nhận và giao lại việc |
| S6 | Đa agent: 3 chuyên gia song song + 1 agent tổng hợp; agent đơn giữ sau `PLANNER_MODE` | Tận dụng nhiều worker; agent đơn là dự phòng và là mốc so sánh |
| S7 | Sharding dữ liệu người dùng theo `user_id % N`, N = 2 cố định | Đây là phần lớn dần theo số User; mọi truy vấn Trip đã lọc theo User |
| S8 | Ghi ưu tiên nhất quán, đọc ưu tiên sẵn sàng; không tự động failover | Trình diễn được CAP; Patroni + etcd là nguồn lỗi lớn nhất trước demo |
| S9 | Thành nhận #14; demo_cache là chế độ `replay` của cache trong `llm-gateway` | Một cơ chế, một nơi |
| S10 | Bằng chứng: trang "Hệ thống" trong app + script load test | Nói được "User này ở shard nào"; không thêm Prometheus/Grafana |
| S11 | Chỉ cache khớp chính xác theo hash(request) | "Đà Lạt 3 ngày 5 triệu" và "Đà Lạt 2 ngày 3 triệu" gần nhau về ngữ nghĩa nhưng phải ra kết quả khác |
| S12 | Mỗi thành phần phân tán bật bằng một biến môi trường; thiếu biến thì chạy như cũ | Chế độ đơn giản là đường lui cho demo, cho test và cho máy các bạn khác |
| S13 | Không chuyển dữ liệu cũ sang cụm; cụm khởi động với volume mới + import Place + script tạo User mẫu | Chỉ là dữ liệu dev (như quyết định ở spec UI mới) |
| S14 | AI tự train: chỉ mô hình mưa. Bỏ động đất, độ đông, cá nhân hoá / recommender | Động đất không dự đoán được về khoa học; độ đông không có dữ liệu kiểm chứng; quỹ thời gian chỉ đủ một mô hình |
| S15 | `DEMO_TODAY` đóng băng "hôm nay" ở `parse_trip` và `forecast` | Prompt đọc yêu cầu có ngày hôm nay; không đóng băng thì bản ghi `replay` trượt cache khi sang ngày khác |
| S16 | `GATEWAY_CHAT_TTL`, `0` = không hết hạn | Bản ghi cho demo và load test phải sống qua nhiều ngày |
| S17 | Dự báo Open-Meteo cache trong Redis (6 giờ; có `DEMO_TODAY` thì không hết hạn và ghi cả kết quả lỗi) | Khả năng mưa nằm trong brief gửi LLM; mất mạng mà brief đổi thì trượt cache |

S13 khác với kế hoạch đã duyệt ("script chuyển dữ liệu"): bỏ script chuyển, thay bằng script tạo dữ liệu mẫu.

## 3. Vấn đề thật → kỹ thuật

| Kỹ thuật | Vấn đề trong Travility | Cách giải | Mục |
|---|---|---|---|
| Rate limit | Gemini free vài request/phút, một lần lập lịch ~13 lượt gọi; một User bấm liên tục làm cạn quota của mọi người | Giới hạn theo User ở `api`; giới hạn theo provider ở `llm-gateway` (chờ thay vì lỗi) | §5.3, §6 |
| Caching | LLM, embedding, Goong đều chậm và tốn tiền; cache Goong đang nằm trong RAM một tiến trình | Redis: phản hồi LLM, embedding, km Goong | §6, §8 |
| Message queue | Lập lịch 10–30 giây giữ một kết nối HTTP và một tiến trình `api` suốt thời gian đó; tiến trình chết là mất việc | Redis Streams: `api` đẩy việc, `planner` xử lý, việc được giao lại khi worker chết | §5 |
| Load balancing | Một tiến trình `api` Python chỉ dùng một nhân CPU | `nginx` chia đều cho 2 bản `api` không giữ trạng thái | §4 |
| Microservice | Bốn loại tải khác nhau nằm chung: request nhẹ, việc LLM dài, gọi provider, tìm vector | 4 service, scale độc lập | §4 |
| Replication | Tìm Place là đọc nhiều, gần như không ghi | Bản sao đọc cho database chung | §9 |
| Sharding | Trip, Itinerary (mỗi lần sửa một version), tin nhắn tăng theo số User | 2 shard theo `user_id` | §9 |
| Distributed system | — | Tổng hợp các mục trên + đa agent chạy trên nhiều worker | §7 |
| CAP | Node chết thì chọn từ chối hay trả dữ liệu cũ? | Chọn theo loại dữ liệu | §10 |

## 4. Kiến trúc

```
client ─► nginx ─► api ×2 ──► redis (Streams · cache · bộ đếm)
                    │              ▲ events          │ jobs / agent_jobs
                    │              │                 ▼
                    │        planner ×2 (điều phối) · planner ×3 (agent)
                    │              │         │
                    │              │         └──► llm-gateway ──► Gemini / OpenAI
                    ├──────────────┴──► places ──► pg-catalog-replica
                    ├──► pg-catalog      users, destinations, places
                    └──► pg-shard-0/1    trips, itineraries, messages, proposals
```

| Service | Lệnh khởi động | Việc | Phụ thuộc |
|---|---|---|---|
| `nginx` | image `nginx` | Chia đều cho các bản `api`; `limit_req` theo IP cho `/auth/*`; tắt buffer cho SSE | `api` |
| `api` | `uvicorn app.main:app` | Auth, Trip, version, ghim, Disruption → Proposal (code, không LLM); đẩy việc vào queue; chuyển event về client; định tuyến shard; `GET /system/status` | redis, pg-catalog, shard, `places` |
| `planner` | `python -m app.worker --stream jobs` / `--stream agent_jobs` | Chạy `parse_trip`, lập lịch, followup, agent chuyên gia | redis, shard, `places`, `llm-gateway` |
| `llm-gateway` | `uvicorn app.gateway:app` | Proxy giao thức OpenAI: cache, giới hạn theo provider, chuyển provider | redis, provider |
| `places` | `uvicorn app.places_service:app` | Tìm Place bằng vector, Place tương tự, lấy Place theo id, km Goong | pg-catalog-replica, redis, `llm-gateway`, Goong |

Tổng 15 container (1 nginx, 2 api, 5 planner, 1 gateway, 1 places, 1 redis, 4 Postgres). Đo RAM cuối T3; nếu chật thì giảm số bản `planner`.

**Hai file compose.** `docker-compose.yml` giữ nguyên (db + api, chế độ đơn giản). `docker-compose.cluster.yml` là cụm đầy đủ. Dev hằng ngày và máy các bạn khác dùng file đầu.

**Chế độ đơn giản (S12).** Bảng dưới là toàn bộ công tắc; thiếu biến nào thì phần đó chạy như hiện nay.

| Biến | Thiếu → | Có → |
|---|---|---|
| `REDIS_URL` | Việc chạy ngay trong request; cache là dict trong RAM; không rate limit | Queue, cache Redis, rate limit |
| `PLACES_URL` | Gọi hàm tìm Place trong cùng tiến trình | Gọi HTTP sang `places` |
| `LLM_BASE_URL` / `EMBED_BASE_URL` | Trỏ thẳng provider (như hiện nay) | Trỏ `http://llm-gateway:8000/v1` |
| `SHARD_URLS` | Mọi bảng ở `DATABASE_URL` | Danh sách URL shard, cách nhau dấu phẩy |
| `CATALOG_REPLICA_URL` | Đọc Place từ `DATABASE_URL` | Đọc Place từ bản sao |
| `PLANNER_MODE` | `single` | `multi` |
| `DEMO_TODAY` | Dùng ngày thật theo giờ VN | Mọi chỗ cần "hôm nay" dùng ngày này |

**Giữ nguyên:** `rules.build_itinerary`, `rules.find_conflicts`, engine thay thế (`replan.py`) không đổi logic. Tiền và Conflict vẫn do code tính ở đúng một nơi (ADR-0001, ADR-0006).

## 5. Queue và luồng lập lịch

### 5.1 Luồng

Hiện tại `trips._stream(run)` chạy generator `run(conn)` ngay trong request và phát từng event SSE. Luồng mới giữ nguyên các generator đó, chỉ đổi nơi chạy:

```
POST /trips (hoặc /trips/{id}/plan, /trips/{id}/replan)
  api:     kiểm JWT, quyền trên Trip (404), rate limit (429), tham số (422)   ← lỗi trả trước khi mở stream, như hiện nay
           job_id = uuid; XADD jobs {job_id, kind, user_id, tham số}
           mở SSE: XREAD events:{job_id} từ đầu, chuyển từng event cho client tới khi gặp event kết thúc
  planner: XREADGROUP jobs → chạy đúng generator hiện có → XADD events:{job_id} cho mỗi event
           xong: SET job:{job_id}:done, XACK
```

- Event kết thúc: `itinerary`, `answer`, `clarify`, `confirm_replan`, `error` (đúng các event cuối hiện nay). `events:{job_id}` hết hạn sau 1 giờ.
- Bất kỳ bản `api` nào cũng đọc được `events:{job_id}`, nên load balancer không cần ghim client vào một bản.
- Client mất kết nối giữa chừng: `GET /jobs/{job_id}/events` phát lại từ đầu stream (cùng định dạng SSE). `api` trả `job_id` trong header `X-Job-Id`. Client hiện tại không cần dùng; thêm vào `api.ts` là việc tuỳ chọn.
- Disruption → Proposal và "Áp dụng" không qua queue: code thuần, dưới 2 giây, chạy trong `api`.

### 5.2 Worker chết và giao lại việc

- Worker đọc bằng consumer group `planners`. Việc chưa `XACK` nằm trong danh sách chờ.
- Mỗi worker định kỳ `XAUTOCLAIM` việc đã chờ quá 60 giây (worker giữ nó đã chết) và chạy lại từ đầu; phát `thinking` "Đang thử lại…".
- Chống lưu trùng: trước khi chạy và trước khi lưu Itinerary, kiểm `job:{job_id}:done`. Đã có thì chỉ `XACK`.
- Chạy lại tối đa 1 lần; lần thứ hai hỏng thì phát `error` và `XACK`.
- Ngữ nghĩa giao việc là "ít nhất một lần". Khe hở còn lại: worker chết sau khi lưu Itinerary nhưng trước khi đặt `done` → có thể sinh hai version giống nhau. Chấp nhận, ghi trong báo cáo.

### 5.3 Rate limit theo User

- Áp cho các endpoint đẩy việc vào queue. Bộ đếm cửa sổ cố định trong Redis: `rl:{user_id}:{phút}`, giới hạn `PLAN_RPM` (mặc định 5).
- Vượt: 429, header `Retry-After`, thông điệp tiếng Việt; client hiện bong bóng đỏ như các lỗi khác.
- Redis lỗi: cho qua (không chặn người dùng vì bộ đếm hỏng).
- `nginx` `limit_req` theo IP cho `/auth/*` để chặn dò mật khẩu.

## 6. `llm-gateway`

Nói giao thức OpenAI ở `POST /v1/chat/completions` và `POST /v1/embeddings` (không streaming — code hiện tại không dùng). Các service khác chỉ đổi `LLM_BASE_URL` / `EMBED_BASE_URL`; `app/llm.py` không sửa (tận dụng ADR-0003). Phản hồi của provider được trả nguyên văn, nên `thought_signature` của Gemini không mất.

**Cache.** Khoá = SHA-256 của thân request đã chuẩn hoá (sắp xếp khoá JSON). Giá trị = thân phản hồi. `GATEWAY_CACHE`:

| Chế độ | Hành vi |
|---|---|
| `off` | Luôn gọi provider |
| `on` (mặc định trong cụm) | Trúng thì trả ngay; trượt thì gọi provider rồi ghi. Chat hết hạn sau `GATEWAY_CHAT_TTL` giây (mặc định 24 giờ, `0` = không hết hạn); embedding không hết hạn |
| `replay` | Chỉ đọc cache; trượt → 503 "chưa ghi phản hồi cho request này". Dùng cho demo mất mạng (#14) và cho load test |

Redis bật `appendonly` và có volume, nên cache sống qua lần khởi động lại. Quy trình demo: đặt `DEMO_TODAY` và `GATEWAY_CHAT_TTL=0`, chạy kịch bản một lần ở chế độ `on` khi có mạng, rồi chuyển `replay` ([runbook](../../runbook-cum.md)).

Hệ quả cần biết: cùng một tin nhắn trên cùng một Trip sẽ ra đúng lịch cũ trong 24 giờ. Chấp nhận cho demo; "Lập lại" vẫn ra lịch khác vì brief có kèm lịch cũ.

**Giới hạn theo provider.** Bộ đếm theo phút trong Redis cho từng provider (`LLM_RPM`). Hết lượt: chờ tới phút sau, tối đa 30 giây, rồi mới trả 429. Mục đích: nhiều agent chạy song song không làm vỡ quota. Chỉ áp cho chat của provider chính; trúng cache không tính lượt.

**Chuyển provider.** Khai báo provider phụ (`LLM2_BASE_URL`, `LLM2_API_KEY`, `LLM2_MODEL`). Provider chính trả 429/5xx/timeout → gọi provider phụ với model tương ứng. Sau 3 lỗi liên tiếp, bỏ qua provider chính 30 giây. **Chỉ áp cho chat.** Embedding không chuyển provider: hai provider cho hai không gian vector khác nhau, đổi là phải import lại Place (ADR-0003).

**Số đếm.** Trúng / trượt cache, lượt gọi provider, lượt phải chờ, lượt chuyển provider — lưu trong Redis, trang "Hệ thống" đọc.

Gateway viết đồng bộ như phần còn lại của server; lượt chờ chiếm một thread trong pool của FastAPI.

## 7. Lập lịch đa agent

Chỉ áp cho lập lịch mới và "Lập lại". `parse_trip`, hỏi lại (`clarify`) và followup (sửa Stop, trả lời câu hỏi) vẫn là một agent như hiện nay.

```
planner (điều phối, stream jobs)
  parse_trip → clarify?  (như cũ)
  PLANNER_MODE=multi:
    XADD agent_jobs × 3: {parent: job_id, role, trip}
    chờ kết quả ở results:{job_id}, tối đa 45 giây
planner (agent, stream agent_jobs) — mỗi role một việc, chạy song song
    vòng lặp tool search_places (tối đa 4 lượt) → submit_shortlist(place_ids, note)
    mỗi lượt tìm phát event tool_call kèm agent=role vào events:{job_id}
    RPUSH results:{job_id}
planner (điều phối)
    gộp 3 danh sách → agent tổng hợp = agent.plan với `seen` nạp sẵn các Place đã chọn
    → submit_itinerary → build_itinerary → vòng sửa như cũ (Draft sai: làm lại 1 lần; có Conflict: sửa 1 lần)
```

| Role | Tìm gì | Danh sách ngắn |
|---|---|---|
| `an-uong` | Quán cho bữa sáng / trưa / tối theo Preference và Budget | ~2 × số bữa của Trip |
| `tham-quan` | Tham quan, cafe, giải trí; ưu tiên trong nhà cho ngày mưa | ~2 × số Stop còn lại theo Pace |
| `cho-o` | Chỗ ở (chỉ khi Trip dài hơn 1 ngày) | 3 |

- **Hai stream tách nhau** (`jobs` cho điều phối, `agent_jobs` cho agent) để không bị kẹt: nếu chung một stream, ba việc lập lịch đồng thời sẽ chiếm hết worker ở vai điều phối và không còn ai chạy agent.
- ADR-0001 vẫn giữ: agent tổng hợp chỉ được dùng Place trong `seen`. Nó được gọi thêm `search_places` tối đa 2 lượt để lấp chỗ thiếu.
- Place đã ghim (khi "Lập lại") được nạp vào `seen` và brief như hiện nay.
- **Dự phòng:** một agent lỗi, hoặc quá 45 giây chưa đủ kết quả → phát `thinking` "Chuyển sang lập lịch thường…" và chạy `agent.plan` đơn như cũ. Người dùng luôn nhận được Itinerary.
- Event `thinking` và `tool_call` thêm trường tuỳ chọn `agent`. Client hiện tại bỏ qua trường lạ, nên không phải sửa; hiện nhãn agent trong Chat là việc tuỳ chọn.
- **Đánh giá:** chạy golden set (kéo một phần #6 lên T4) ở cả `single` và `multi`, báo: % Itinerary hợp lệ, số Conflict, thời gian, số lượt gọi LLM. `multi` chỉ thành mặc định của demo nếu không kém `single` về % hợp lệ.

## 8. `places`

| Endpoint | Thay cho | Ghi chú |
|---|---|---|
| `POST /search` | `agent.run_search` phần truy vấn pgvector | Embed truy vấn qua `llm-gateway`; lọc Destination, Tag bắt buộc / tránh như hiện nay |
| `POST /similar` | `similar_places` của engine thay thế | Dùng embedding đã lưu, không gọi LLM |
| `GET /places?ids=` | Đọc Place theo id khi mở Trip | — |
| `GET /destinations` | Danh sách Destination + Hub | — |
| `POST /distance` | `distance.prefetch` | Gọi Goong; cache km/phút trong Redis thay cho dict trong RAM của #7; cooldown 60 giây khi Goong lỗi giữ nguyên |

- `places` đọc từ `CATALOG_REPLICA_URL`; bản sao chết thì đọc node chính.
- `places` chết: lập lịch và mở Trip trả lỗi rõ ràng; `POST /distance` lỗi thì `make_leg` dùng chim bay × 1.3 như hiện nay.
- Thiếu `PLACES_URL`: các hàm trên chạy trong cùng tiến trình. Một lớp mỏng `app/places_client.py` chọn giữa hai cách; code gọi không biết khác biệt.
- `scripts/import_places` ghi vào node chính của pg-catalog.

## 9. Dữ liệu

### 9.1 Chia bảng

| Database | Bảng | Bản sao |
|---|---|---|
| `pg-catalog` (chính) | `users`, `destinations`, `places` | `pg-catalog-replica`, streaming replication bất đồng bộ |
| `pg-shard-0`, `pg-shard-1` | `trips`, `itineraries`, `proposals`, `messages` | Không |

- `shard = user_id % N`, với N = số URL trong `SHARD_URLS`. `db.shard_conn(user_id)` trả kết nối; mọi handler Trip đã có `user_id` từ JWT.
- Dependency `get_conn` tách thành `get_catalog` và `get_shard`. Thiếu `SHARD_URLS` thì cả hai trả kết nối tới `DATABASE_URL`.
- `schema.sql` tách thành `schema_catalog.sql` và `schema_shard.sql`; chế độ đơn giản áp cả hai lên một database.
- Khoá ngoại `trips.user_id → users(id)` bị bỏ (khác database). Toàn vẹn do code giữ: `user_id` luôn lấy từ JWT đã kiểm.
- Truy vấn nối bảng người dùng với bảng chung phải tách làm hai. Hiện có một chỗ: `trips.py` `trips LEFT JOIN destinations`.
- `trips.id` là số tự tăng theo từng shard, nên hai shard có thể trùng id. Không sao: `/trips/{id}` luôn đi kèm JWT, shard xác định từ User trước rồi mới tra id. `job_id` là uuid.
- Thêm shard thứ ba đòi chuyển dữ liệu (phép chia dư đổi kết quả với hầu hết User). Không làm; báo cáo trình bày consistent hashing là hướng giải.

### 9.2 Replication

- Image `pgvector/pgvector:pg17` cho cả hai node. Node chính: `wal_level=replica`. Bản sao khởi tạo bằng `pg_basebackup` trong script entrypoint, chạy ở chế độ hot standby.
- Bất đồng bộ → bản sao có thể trễ. Chỉ Place được đọc từ bản sao; Place gần như không đổi nên dữ liệu trễ vô hại.
- Trang "Hệ thống" hiện độ trễ bản sao.

### 9.3 Khởi tạo cụm

Volume mới → áp schema → `import_places` → `scripts/seed_users` tạo vài User mẫu rơi vào cả hai shard. Không chuyển dữ liệu từ database đơn (S13).

## 10. CAP: hành vi khi node chết

Lựa chọn theo loại dữ liệu ([ADR-0008](../../adr/0008-cap-theo-loai-du-lieu.md)):

| Dữ liệu | Ưu tiên | Cách làm |
|---|---|---|
| Ghim, version Itinerary, áp dụng Proposal | Nhất quán | Ghi và đọc ở node chính của shard, trong một transaction; version lệch → 409 như hiện nay |
| Tài khoản (đăng ký) | Nhất quán | Chỉ ghi vào node chính pg-catalog |
| Đăng nhập | Sẵn sàng | Đọc node chính; node chính chết thì đọc bản sao |
| Place, Destination | Sẵn sàng | Đọc bản sao, chấp nhận trễ |
| Cache LLM / Goong, bộ đếm | Sẵn sàng | Redis lỗi thì bỏ qua cache, không chặn |

| Node chết | Hệ thống |
|---|---|
| Một bản `api` | `nginx` dồn sang bản còn lại; SSE đang mở ở bản chết bị đứt, client nối lại bằng `job_id` |
| Một `planner` đang chạy việc | Việc được worker khác nhận lại sau 60 giây (§5.2) |
| `pg-catalog-replica` | `places` đọc node chính; người dùng không thấy gì |
| `pg-catalog` (chính) | Chế độ chỉ đọc cho dữ liệu chung: không đăng ký được (503 kèm thông báo). Đăng nhập, tìm Place, **lập lịch và sửa lịch vẫn chạy** vì Trip nằm ở shard |
| Một shard | User của shard đó nhận 503 "dữ liệu chuyến đi tạm không truy cập được"; User shard kia không bị ảnh hưởng |
| `redis` | Không lập lịch được (503); xem Trip, ghim, Disruption → Proposal vẫn chạy; rate limit cho qua |
| `llm-gateway` hoặc provider | Việc lỗi → thử lại 1 lần → event `error` như hiện nay |
| `places` | Lập lịch và mở Trip báo lỗi; km quay về ước tính |

Bật lại node bằng tay (`docker compose start`). Không có bầu chọn node chính.

## 11. Mô hình dự đoán mưa (T7)

**Bài toán.** `forecast.get_rain_chance` trả `None` khi ngày đi xa hơn 16 ngày (ngoài tầm Open-Meteo) → Trip đặt trước không có thông tin mưa, Conflict `rain_outdoor` không bao giờ bật. Mô hình trả xác suất có mưa (≥ 1 mm) cho từng ngày tại Destination, đổ vào đúng trường `rain_chance` sẵn có.

**Dữ liệu (Thành thu thập).** Open-Meteo Historical (ERA5) theo ngày từ 1990 tại toạ độ Destination; chỉ số ENSO (ONI) theo tháng của NOAA. Script `server/ml/rain/fetch.py` tải và lưu CSV thô; không commit dữ liệu thô nếu lớn, commit script và checksum.

**Đặc trưng.** Ngày trong năm (sin/cos), tháng, ONI của các tháng **trước** ngày dự đoán (trễ đủ để có lúc dự đoán thật), tần suất mưa lịch sử của ngày đó tính **chỉ từ các năm trước** năm đang xét. Không dùng bất kỳ quan trắc nào của chính ngày đó hay sau đó.

**Mô hình và mốc so sánh.** XGBoost phân loại nhị phân. Mốc: tần suất mưa trung bình của ngày đó trong các năm huấn luyện (climatology). Nói thẳng trong báo cáo: ở tầm xa hơn 16 ngày, mô hình chỉ có thể nhỉnh hơn mốc; nếu không thắng mốc trên Brier score thì **phát hành chính mốc đó** và ghi rõ.

**Kiểm định.** Walk-forward theo năm (huấn luyện tới năm Y, kiểm trên năm Y+1), không trộn ngẫu nhiên. Đo Brier score, AUC, biểu đồ hiệu chỉnh. Áp skill `godchi:ml-data-leakage-guard`, `godchi:walk-forward-guard`, `godchi:model-feature-versioning`.

**Giải thích.** Đóng góp từng đặc trưng lấy từ `pred_contribs` của XGBoost (không thêm thư viện SHAP) → một câu tiếng Việt do code ghép, ví dụ "Khả năng mưa 72%: tháng 10 là cao điểm mùa mưa (8/10 năm gần đây ngày này có mưa), La Niña làm tăng thêm". LLM không viết câu này.

**Tích hợp.**
- File mô hình `server/models/rain-<destination>-v<N>.json` kèm file mô tả (đặc trưng, khoảng năm huấn luyện, chỉ số kiểm định). Nạp trong `app/forecast.py`.
- Ngày trong 16 ngày tới: Open-Meteo như cũ. Xa hơn: mô hình. Không có file mô hình hoặc lỗi: `None` như hiện nay.
- `Day` thêm `rain_source` (`forecast` | `model`) và `rain_note` (câu giải thích). Timeline hiện nhãn nguồn và câu giải thích cạnh % mưa — thay đổi client duy nhất của lát này, do Thành làm.
- Không thêm service.

## 12. Trang "Hệ thống", load test, kịch bản demo

**`GET /system/status`** (cần đăng nhập) trả: danh sách node kèm sống/chết, bản `api` vừa phục vụ (hostname), độ dài queue + số việc đang chờ + số worker, trúng/trượt cache, số lượt bị rate limit, số lượt chuyển provider, độ trễ bản sao, shard của User hiện tại, `PLANNER_MODE`. Chế độ đơn giản trả một node.

**Trang trong app:** thêm một nút trên rail mở sơ đồ cụm, tự làm mới mỗi 2 giây; node chết đổi màu.

**Load test:** `server/scripts/loadtest.py` (asyncio + httpx, không thêm công cụ). Kịch bản: đăng nhập, xem danh sách Trip, mở Trip, lập lịch với gateway ở `replay`. In bảng p50 / p95 / request mỗi giây.

| Kỹ thuật | Trình diễn |
|---|---|
| Load balancing | Bảng load test 1 bản vs 2 bản `api`; trang "Hệ thống" đổi tên bản phục vụ qua từng request |
| Caching | Lập cùng một Trip hai lần: lần hai nhanh rõ rệt, số "trúng cache" tăng; bảng load test cache tắt vs bật |
| Rate limit | Gửi 6 yêu cầu lập lịch trong một phút → lần thứ 6 báo 429 |
| Message queue | Tắt một `planner` giữa lúc lập lịch → việc được nhận lại và hoàn tất |
| Microservice | `docker compose ps` + sơ đồ; tắt `places` → chỉ lập lịch lỗi, đăng nhập và xem tài khoản vẫn chạy |
| Replication | Tắt bản sao → không ai thấy gì; trang hiện độ trễ |
| Sharding | Hai User mẫu ở hai shard; tắt một shard → chỉ một người lỗi |
| CAP | Tắt `pg-catalog` → không đăng ký được nhưng vẫn lập lịch |
| Đa agent | Pin của ba agent hiện đồng thời trên map; bảng so `single` vs `multi` |
| Mô hình mưa | Trip đi sau 2 tháng có % mưa kèm câu giải thích và nhãn "mô hình" |

## 13. Test

- 203 test hiện có chạy ở chế độ đơn giản, không đổi. Đây là điều kiện bắt buộc cuối mỗi tuần.
- Test mới cần Redis thật: thêm service `redis` vào `docker-compose.yml` (chỉ để test dùng; `api` ở chế độ đơn giản không trỏ tới). Không dùng thư viện giả lập Redis.
- `llm-gateway`: provider giả bằng `httpx.MockTransport` — trúng/trượt cache, `replay` trượt → 503, chờ khi hết lượt, chuyển provider, embedding không chuyển provider.
- Queue: việc chạy xong phát đủ event theo thứ tự; việc bị bỏ dở được nhận lại; không lưu trùng khi đã có `done`.
- Định tuyến shard: hai database test; User chẵn / lẻ nằm đúng shard; User shard này không đọc được Trip shard kia.
- Đa agent: LLM giả (`tests/fakes.py`) cho từng role; một agent lỗi → quay về agent đơn.
- Mô hình mưa: test rò rỉ (đặc trưng của ngày D không đổi khi sửa dữ liệu từ ngày D trở đi), test câu giải thích, test `forecast` chọn đúng nguồn theo khoảng cách ngày.
- `scripts/smoke_cluster.sh`: dựng cụm, chạy một lượt lập lịch ở `replay`, kiểm `GET /system/status`. Các kịch bản tắt node là runbook chạy tay, ghi trong `docs/`.

## 14. Lộ trình và nghiệm thu

| Tuần | Giao | Nghiệm thu |
|---|---|---|
| T2 | Redis; `llm-gateway` (proxy, cache, `replay` #14, giới hạn provider, chuyển provider); cache Goong sang Redis | `api` trỏ qua gateway lập lịch được; lập lại cùng request trúng cache; `replay` chạy kịch bản khi tắt mạng |
| T3 | Queue + `planner` chạy agent đơn; SSE qua Redis; `nginx` + 2 `api`; rate limit theo User | Client không sửa vẫn lập lịch qua cụm; tắt `planner` giữa chừng việc vẫn xong; lần thứ 6 trong phút → 429 |
| T4 | Agent chuyên gia + tổng hợp; `PLANNER_MODE`; so sánh bằng golden set | Bảng `single` vs `multi`; một agent lỗi vẫn ra Itinerary |
| T5 | `places`; bản sao đọc; 2 shard + định tuyến; script tạo User mẫu | Tắt bản sao / một shard cho đúng hành vi §10 |
| T6 | Trang "Hệ thống"; load test; chế độ chỉ đọc; runbook tắt node; **đóng băng kiến trúc** | Chạy được toàn bộ bảng trình diễn §12 (trừ mô hình mưa) |
| T7 | Mô hình mưa | Báo cáo kiểm định có mốc so sánh; Trip xa hơn 16 ngày có % mưa + giải thích |

Thứ tự cắt nếu trễ: sharding → tách `places` → đa agent (về `single`). Mô hình mưa độc lập với hạ tầng, cắt được riêng.

Mỗi tuần một plan riêng (`superpowers:writing-plans`), viết khi bắt đầu tuần đó.

## 15. Rủi ro

| Rủi ro | Xử lý |
|---|---|
| T8 (#37 + #26) không còn tuần đệm | #26 là thứ cắt đầu tiên |
| 15 container quá nặng cho một Mac | Đo cuối T3; giảm bản `planner`; chế độ đơn giản là đường lui |
| Đa agent kém hơn agent đơn | Cờ `PLANNER_MODE`; chỉ bật khi golden set không kém |
| Đa agent tốn quota LLM | Giới hạn theo provider ở gateway; load test và demo dùng `replay` |
| Cache trả lịch cũ khi người dùng muốn lịch mới | Hết hạn 24 giờ; "Lập lại" có brief khác nên không trúng cache |
| Trên một laptop, lợi ích của 2 bản `api` có thể không rõ | Load test dùng kịch bản nặng CPU (`build_itinerary`, mở Trip nhiều version); báo số thật kể cả khi lợi ích nhỏ |
| Các bạn khác vấp cụm khi dev | `docker-compose.yml` mặc định không đổi |
| Mô hình mưa không thắng mốc | Phát hành mốc, ghi rõ trong báo cáo |
