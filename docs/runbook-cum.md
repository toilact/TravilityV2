# Runbook cụm Travility

Cụm phân tán chạy bằng `docker-compose.cluster.yml` ([spec](superpowers/specs/2026-10-01-scale-he-phan-tan-design.md)). Dev hằng ngày vẫn dùng `docker compose up` (một tiến trình). Hai chế độ dùng chung cổng nên chỉ bật một.

## Dựng cụm

```bash
docker compose down                                        # tắt chế độ một tiến trình nếu đang chạy
docker compose -f docker-compose.cluster.yml up -d --build
cd server && uv run python -m scripts.import_places ../data/places   # lần đầu: volume mới chưa có Place
```

`nginx` (trước 2 bản `api`) ở `localhost:8000`, `llm-gateway` ở `localhost:8001` (chỉ để kiểm tra). Mọi lệnh dưới đây viết tắt `dc` = `docker compose -f docker-compose.cluster.yml`.

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

Việc chạy lại tối đa một lần. Tắt cả hai `planner` thì request báo lỗi sau 120 giây; việc vẫn nằm trong queue và sẽ chạy khi `planner` bật lại.

### Rate limit

Mỗi User tối đa `PLAN_RPM` (mặc định 5) tin nhắn / lập lịch mỗi phút; vượt → 429 kèm `Retry-After`. Đổi cho một lần chạy: `PLAN_RPM=20 dc up -d`. Số lần bị chặn: `dc exec redis redis-cli get rl:blocked`.

`/auth/*` bị `nginx` giới hạn 1 request/giây theo IP (burst 10).

### Phát lại tiến trình của một việc

```bash
curl -N localhost:8000/jobs/<X-Job-Id>/events -H "Authorization: Bearer <token>"
```

Việc sống 1 giờ. User khác hoặc việc đã hết hạn → 404.

### Lưu ý

- Bật lại một bản `api` mà `nginx` không chuyển request tới: `dc restart nginx` (nginx chỉ phân giải tên `api` lúc khởi động).
- `redis-cli flushdb` xoá cả queue và việc đang chạy; `planner` tự tạo lại consumer group.
