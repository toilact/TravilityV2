# Runbook cụm Travility

Cụm phân tán chạy bằng `docker-compose.cluster.yml` ([spec](superpowers/specs/2026-10-01-scale-he-phan-tan-design.md)). Dev hằng ngày vẫn dùng `docker compose up` (một tiến trình). Hai chế độ dùng chung cổng nên chỉ bật một.

## Dựng cụm

```bash
docker compose down                                        # tắt chế độ một tiến trình nếu đang chạy
docker compose -f docker-compose.cluster.yml up -d --build
cd server && uv run python -m scripts.import_places ../data/places   # lần đầu: volume mới chưa có Place
docker compose -f ../docker-compose.cluster.yml exec api uv run --no-dev python -m scripts.seed_users   # User mẫu
```

`nginx` (trước 2 bản `api`) ở `localhost:8000`, `llm-gateway` ở `localhost:8001`, `places` ở `localhost:8002` (hai cổng sau chỉ để kiểm tra), `pg-catalog` ở `localhost:5432`. Mọi lệnh dưới đây viết tắt `dc` = `docker compose -f docker-compose.cluster.yml`.

## Số đếm của gateway

```bash
dc exec redis redis-cli mget gw:stat:hit gw:stat:miss gw:stat:provider_call gw:stat:wait gw:stat:fallback
```

## Ghi kịch bản demo rồi phát lại khi mất mạng

Request LLM phải lặp lại y nguyên mới trúng cache, nên "hôm nay" phải cố định và database không được import lại giữa lúc ghi và lúc phát.

1. Chọn ngày ghi, ví dụ hôm nay. Bật cụm ở chế độ ghi, không hết hạn:
   ```bash
   DEMO_TODAY=2026-10-01 GATEWAY_CACHE=on GATEWAY_CHAT_TTL=0 dc up -d
   ```
2. Có mạng: chạy đúng kịch bản demo trong app, từng tin nhắn theo đúng thứ tự, trên Trip mới.
3. Chuyển sang phát lại (giữ nguyên `DEMO_TODAY`):
   ```bash
   DEMO_TODAY=2026-10-01 GATEWAY_CACHE=replay dc up -d
   ```
4. Tắt mạng, tạo Trip mới, chạy lại kịch bản. Tin nhắn ngoài kịch bản → bong bóng lỗi (gateway trả 503).

Ngày đi trong kịch bản nên nằm trong 16 ngày kể từ `DEMO_TODAY` để có dự báo mưa. Kết quả dự báo lúc ghi (kể cả lỗi) được giữ lại cho lúc phát.

## Xoá cache

```bash
dc exec redis sh -c "redis-cli --scan --pattern 'gw:cache:*' | xargs -r redis-cli del"   # chỉ cache LLM/embedding
dc exec redis redis-cli flushdb                                                           # mọi thứ: cache, km Goong, dự báo, số đếm
```

## Queue và planner (T3)

Cụm có 2 bản `api` sau `nginx` (cổng 8000) và 2 `planner`. Header `X-Upstream` của mọi phản hồi cho biết bản `api` nào phục vụ.

```bash
dc exec redis redis-cli xlen jobs                          # số việc đã đẩy (tối đa ~1000 mục gần nhất)
dc exec redis redis-cli xpending jobs planners - + 10      # việc đang chạy: id, planner giữ nó, ms im lặng, số lần giao
dc logs -f planner
```

### Tắt một planner giữa lúc lập lịch

1. Gửi một yêu cầu lập lịch trong app. Dùng câu chưa từng gửi: câu đã có trong cache của gateway chạy xong trước khi kịp tắt.
2. `dc exec redis redis-cli xpending jobs planners - + 10` → dòng thứ hai là id container đang giữ việc.
3. `docker kill <id>`.
4. Sau khoảng 20 giây Chat hiện "Đang thử lại…", rồi ra lịch. Danh sách chuyến đi chỉ có một Trip.
5. Bật lại: `dc up -d`.

Việc chạy lại tối đa một lần. Tắt cả hai `planner` thì request báo lỗi sau 120 giây; việc đã chờ quá 120 giây bị bỏ khi `planner` bật lại, không chạy muộn.

### Rate limit

Mỗi User tối đa `PLAN_RPM` (mặc định 5) tin nhắn / lập lịch mỗi phút; vượt → 429 kèm `Retry-After`. Đổi cho một lần chạy: `PLAN_RPM=20 dc up -d`. Số lần bị chặn: `dc exec redis redis-cli get rl:blocked`.

`/auth/*` bị `nginx` giới hạn 1 request/giây theo IP (burst 10).

### Phát lại tiến trình của một việc

```bash
curl -N localhost:8000/jobs/<X-Job-Id>/events -H "Authorization: Bearer <token>"
```

Việc sống 1 giờ. User khác hoặc việc đã hết hạn → 404.

### Lưu ý

- Bật lại hoặc build lại `api` mà `nginx` trả 502 hay không chuyển request tới: `dc restart nginx` (nginx chỉ phân giải tên `api` lúc khởi động).
- Mỗi stream SSE đang mở giữ một thread của bản `api` (pool 40 thread mỗi bản): khoảng 80 lượt lập lịch đồng thời là trần của cụm 2 `api`.
- `redis-cli flushdb` xoá cả queue và việc đang chạy; `planner` tự tạo lại consumer group.

## `places`, bản sao đọc, shard (T5)

Bốn Postgres: `pg-catalog` (users, destinations, places) có bản sao `pg-catalog-replica`; `pg-shard-0` và `pg-shard-1` giữ trips, itineraries, proposals, messages. Trip của User nằm ở shard `user_id % 2`. Đọc Place đi qua service `places`, service này đọc bản sao.

```bash
dc exec api uv run --no-dev python -m scripts.seed_users          # demo1/demo2@travility.vn, mật khẩu travility-demo; in shard của từng User
dc exec pg-shard-0 psql -U travility -c 'SELECT id, user_id FROM trips'
dc exec pg-catalog-replica psql -U travility -c "SELECT pg_is_in_recovery(), now() - pg_last_xact_replay_timestamp() AS tre"
dc logs places | grep -c "POST /search"                           # số lượt tìm Place đã đi qua service
```

### Tắt bản sao

`dc stop pg-catalog-replica` → không ai thấy gì: `places` đọc node chính, đo được vẫn khoảng 10 ms mỗi lượt đọc (`dc logs places` có dòng "bản sao pg-catalog không kết nối được, đọc node chính"). `dc start pg-catalog-replica` là bản sao tự đuổi kịp.

### Tắt một shard

`dc stop pg-shard-1` → User có `user_id` lẻ nhận 503 "Dữ liệu chuyến đi tạm không truy cập được" ở mọi request về Trip; User chẵn dùng bình thường; đăng nhập của cả hai vẫn chạy. Việc lập lịch đang xếp hàng của User shard chết nhận event `error`, worker chạy tiếp việc khác. Shard không có bản sao: bật lại bằng `dc start pg-shard-1`.

### Tắt `places`

`dc stop places` → lập lịch, Disruption → Proposal, khôi phục version báo "Dịch vụ địa điểm tạm không truy cập được". Danh sách Trip, mở Trip, ghim vẫn chạy (mỗi bản `api` giữ bản Destination đọc được gần nhất, nạp sẵn lúc khởi động). Km của Leg quay về ước tính chim bay × 1.3.

### Lưu ý

- Volume mới hoàn toàn: sau `dc down -v` phải chạy lại `import_places` và `seed_users`. Volume `travility-cluster_pgdata` của T2–T4 không còn được dùng; xoá bằng `docker volume rm travility-cluster_pgdata` nếu không cần dữ liệu cũ.
- `import_places` chạy từ máy ngoài, ghi vào `pg-catalog` qua `localhost:5432`; bản sao nhận theo sau vài mili giây.
- `trips.id` tự tăng theo từng shard nên hai User khác shard có thể cùng có Trip số 1. Không lẫn: shard chọn theo User trong JWT trước rồi mới tra id.
- Node treo mà không tắt hẳn (`docker pause`, đứt mạng) thì mỗi lần kết nối chờ tối đa 2 giây rồi mới chuyển sang node khác hoặc báo 503.
- Thêm shard thứ ba đòi chuyển dữ liệu (`user_id % N` đổi kết quả với hầu hết User): không làm; hướng giải là consistent hashing.
- Chưa có ở T5 (để T6): `pg-catalog` chính chết thì `api` không khởi động lại được và không đăng nhập được.

## Lập lịch đa agent (T4)

`PLANNER_MODE=multi`: ba agent chuyên gia (`an-uong`, `tham-quan`, `cho-o`) tìm Place song song, agent tổng hợp xếp lịch. Chỉ áp cho lập lịch mới và "Lập lại". Mặc định là `single`.

```bash
PLANNER_MODE=multi dc up -d          # cụm: 3 bản planner-agent đọc stream agent_jobs
dc logs -f planner-agent             # mỗi role một dòng "agent <role> xong việc …"
dc exec redis redis-cli xlen agent_jobs
```

Chế độ một tiến trình: đặt `PLANNER_MODE=multi` trong `server/.env`. Không cần Redis; ba agent chạy bằng 3 thread.

Trong Chat, mỗi dòng tìm kiếm có nhãn agent: "Ăn uống · Đang tìm: …", "Tham quan · …", "Chỗ ở · …". Trip 1 ngày không có agent chỗ ở.

### Tắt agent giữa lúc lập lịch

1. `dc stop planner-agent`, rồi gửi một yêu cầu lập lịch chưa từng gửi.
2. Điều phối chờ tối đa 45 giây rồi chạy agent đơn; Chat hiện "Chuyển sang lập lịch thường…" kèm các dòng tìm kiếm của agent đơn, rồi ra lịch (đo được: khoảng 56 giây cho cả lượt).
3. `dc start planner-agent`.

Một agent báo lỗi thì chuyển ngay, không chờ 45 giây. Việc trong `agent_jobs` giao nhiều nhất một lần; việc xếp hàng quá 45 giây bị agent bỏ qua.

### Hạn mức provider

Gemini free cho 15 lượt chat mỗi phút cho mỗi model. Một lần lập lịch `multi` dùng trung bình 15 lượt (10–18), `single` trung bình 6 lượt (5–8), nên một lần `multi` đã xấp xỉ trần và hai lần trong cùng một phút chắc chắn vượt: agent nhận 429, điều phối quay về agent đơn, agent đơn cũng 429 và Chat báo "Không kết nối được AI". Cách xử lý:

- Demo và load test: ghi kịch bản một lần rồi chạy `GATEWAY_CACHE=replay` (mục "Ghi kịch bản demo"). Brief của agent tổng hợp gộp danh sách theo thứ tự role cố định nên phát lại trúng cache.
- Chạy thật: đặt `LLM_RPM=14` để gateway chờ thay vì lỗi; chờ lâu hơn 45 giây thì vẫn rơi về agent đơn.

Đã kiểm ngày 2026-10-01: ba User gửi ba yêu cầu đã ghi cùng lúc → cả ba ra lịch qua đa agent, không lượt nào trượt cache.

### So `single` với `multi`

```bash
docker compose up -d db redis
cd server && uv run python -m scripts.golden --mode both --rpm 14
```

8 prompt, gọi thẳng provider trong `.env`, đa agent chạy bằng thread. `--rpm 14` hãm theo hạn mức Gemini free; thời gian báo đã trừ phần chờ hạn mức.

Kết quả đo ngày 2026-10-01, model `gemini-3.5-flash-lite`, 37 Place Đà Lạt:

| Chế độ | Prompt | Itinerary hợp lệ | Conflict TB | Giây TB | Giây trung vị | Lượt LLM TB | Về dự phòng |
|---|---|---|---|---|---|---|---|
| single | 8 | 100% | 0,6 | 28,4 | 15,0 | 6,4 | 0 |
| multi | 8 | 100% | 1,1 | 21,9 | 19,5 | 15,1 | 1 |

- Trung bình của `single` bị một prompt kéo lên (127 giây, provider trả chậm một lượt); bảy prompt còn lại từ 9 đến 17 giây. So bằng trung vị thì `multi` chậm hơn khoảng 4,5 giây.
- `multi` tốn gấp 2,4 lần số lượt LLM và có nhiều Conflict hơn. Năm trong tám prompt `multi` bị hãm giữa chừng vì vượt 14 lượt mỗi phút; lần về dự phòng duy nhất là do chờ hạn mức quá 45 giây. Thời gian của các prompt bị hãm chỉ là xấp xỉ.
- Kết luận: trên dữ liệu và hạn mức hiện tại `multi` không hơn `single` ở chỉ số nào. Giữ `single` làm mặc định, kể cả cho demo; `multi` dùng để trình diễn agent chạy song song trên nhiều worker (chạy ở `replay`).
