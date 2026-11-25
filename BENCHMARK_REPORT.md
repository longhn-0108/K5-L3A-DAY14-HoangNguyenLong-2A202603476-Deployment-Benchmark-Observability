# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Hoàng Nguyên Long (MSSV: 2A202603476)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 Ubuntu (Python 3.12.3), Docker Desktop v29.9.2

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < **500** ms | Đảm bảo 95% người dùng nhận được phản hồi gần như tức thời (< 0.5 giây); dùng p95 thay vì average để kiểm soát tail latency mà vẫn không quá nhạy với 1–3% spike ngẫu nhiên từ upstream LLM. |
| Error rate `/ask` | < **2.0** % | Chấp nhận error budget 2% cho các lỗi mạng/upstream LLM tạm thời (`503 Service Unavailable`, mặc định mock lỗi ~1%), nếu vượt 2% nghĩa là hệ thống hoặc upstream đang gặp sự cố bất thường. |
| Accuracy trên golden dataset | ≥ **85.0** % (sau khi sửa KB: **100.0** %) | Đảm bảo chất lượng câu trả lời RAG trên bộ 23 câu hỏi chuẩn (golden dataset) đạt độ chính xác cao và không có bất kỳ câu nào bị regression so với phiên bản baseline trước khi cho phép merge/deploy. |

### Trả lời câu hỏi Exercise 7.1 (Prometheus Metrics & Cardinality trong `develop/app.py`)
1. **Ví dụ cho mỗi loại metric (`Counter`, `Gauge`, `Histogram`) trong output `GET /metrics`:**
   - **`Counter`** (chỉ tăng đơn điệu, reset khi process khởi động lại): `http_requests_total{method="POST",path="/ask",status="200"}`, `llm_tokens_total{direction="input",model="mock-llm-small"}`, `llm_cost_usd_total{model="mock-llm-small"}`.
   - **`Gauge`** (có thể tăng hoặc giảm theo trạng thái tức thời): `http_requests_in_flight` (số request đang được xử lý đồng thời), `agent_info{model="mock-llm-small",version="v2"}`.
   - **`Histogram`** (phân phối giá trị chia theo các bucket `_bucket{le="..."}` kèm `_sum` và `_count`): `http_request_duration_seconds_bucket{method="POST",path="/ask",le="0.5"}`, `llm_call_duration_seconds_bucket`, và metric mới thêm `agent_question_length_chars_bucket{le="100.0"}`.
2. **Điều gì xảy ra nếu trong middleware thay `route.path` bằng `request.url.path` khi có bot scan hàng nghìn URL ngẫu nhiên (`/ask/1`, `/ask/2`, `/wp-admin`, ...)?**
   - Sẽ xảy ra hiện tượng **Cardinality Explosion (bùng nổ số lượng chuỗi thời gian)**: Trong Prometheus, mỗi tổ hợp nhãn `(method, path, status)` mới sẽ tạo ra một time-series riêng biệt trong RAM (với Histogram có ~10 buckets thì mỗi URL ngẫu nhiên tạo thêm ~12 time-series). Khi bot quét hàng chục nghìn URL ngẫu nhiên không khớp route nào, `request.url.path` lưu nguyên chuỗi URL thô vào label `path`, làm số lượng time-series tăng vọt lên hàng trăm nghìn, gây **tràn bộ nhớ RAM (OOM)** cho cả agent lẫn Prometheus server. Ngược lại, dùng `route.path` gom toàn bộ các URL không tồn tại về một nhãn cố định duy nhất là `"unmatched"`.

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.9 | 189.0 | 222.4 | 1707.1 | 1.00% (`297×200`, `3×503`) | ✅ PASS |
| 10 | 34.82 | 192.7 | 226.1 | 1707.5 | 0.67% (`298×200`, `2×503`) | ✅ PASS |
| 50 | 124.99 | 202.4 | 294.0 | 322.7 | 1.00% (`297×200`, `3×503`) | ✅ PASS |
| 100 | 41.4 | 1023.6 | 5117.9 | 5423.4 | 1.00% (`297×200`, `3×503`) | ❌ FAIL (`p95 > 500ms`) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- Từ `concurrency = 1` lên `10` và `50`, RPS tăng gần tuyến tính (`3.9` → `34.82` → `124.99 req/s`) trong khi `p50` chỉ nhích nhẹ (`189.0 ms` → `202.4 ms`), bởi vì `app.py` sử dụng `async def` và `asyncio.sleep()` không chặn (non-blocking I/O) nên 1 worker Uvicorn có thể phục vụ đồng thời nhiều kết nối đang chờ I/O của bước retrieval và LLM.
- Tuy nhiên khi tăng lên `concurrency = 100`, RPS **không còn tăng tuyến tính mà sụt giảm mạnh xuống `41.4 req/s`**, đồng thời latency vọt lên (`p50 = 1023.6 ms`, `p95 = 5117.9 ms` → **FAIL SLO**). Nguyên nhân là sự bão hòa (saturation) tại tầng event loop / socket backlog của 1 tiến trình Uvicorn đơn lẻ và giới hạn connection pool: hàng trăm request đến cùng lúc phải xếp hàng chờ xử lý (queuing delay theo định luật Little: $L = \lambda W$), làm thời gian phản hồi tăng vọt.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 195.2 | 223.1 | 250.1 |
| 0.03 (mặc định) | 218.8 | 227.6 | 1684.7 |
| 0.1 | 324.0 | 1678.8 | 1719.5 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **Chỉ số nhạy nhất**:
  - Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (3% request bị chậm thêm `1500 ms`), **`p99`** nhạy nhất: nhảy vọt từ **`250.1 ms` lên `1684.7 ms`** (tăng gần 7 lần), trong khi `avg` chỉ tăng nhẹ từ `195.2 ms` lên `218.8 ms` (+23.6 ms) và `p95` gần như giữ nguyên (`227.6 ms` vì 3% lỗi chậm nằm ngoài ngưỡng 95%).
  - Khi `MOCK_SLOW_RATE = 0.1` (10% request chậm > 5%), cả **`p95` (`1678.8 ms`)** và **`p99` (`1719.5 ms`)** đều nhảy vọt lên ngưỡng ~1.7 giây (vi phạm SLO `p95 ≤ 500 ms`), nhưng **`avg` vẫn chỉ ở mức `324.0 ms`** (nhìn qua tưởng vẫn đạt `< 500 ms`!).
- **Vì sao SLO không nên đặt theo average**: Trung bình cộng (`avg`) san phẳng và che giấu hoàn toàn **tail latency** (nhóm 1%–10% khách hàng phải chờ gần 2 giây). Đặt SLO theo percentile (`p95`, `p99`) mới phản ánh đúng trải nghiệm thực tế của nhóm người dùng chịu độ trễ cao nhất.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | **4.3%** (`1/23`) | **91.3%** (`21/23`) | **100.0%** (`23/23`) |
| Avg tokens / câu | 56.7 | 109.0 | 113.7 |
| Tổng cost (USD) | $0.000399 | $0.000759 | $0.000790 |
| Cost / câu đúng (USD) | $0.00039855 | $0.00003616 | $0.00003436 |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ PASS (với `--min-accuracy 1.0`) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` (*"JWT khác gì API key trong xác thực?"*) | `["token", "hết hạn", "chữ ký"]` | Thêm tài liệu về `["jwt"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`: *"API key là chuỗi bí mật cố định, không tự hết hạn. JWT là token có chữ ký số, chứa thông tin user và thời điểm hết hạn; server xác minh chữ ký mà không cần tra database."* |
| `scaling-03` (*"Kubernetes HPA scale dựa trên những chỉ số nào?"*) | `["cpu", "memory", "custom metrics"]` | Thêm tài liệu về `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`: *"Kubernetes HPA (Horizontal Pod Autoscaler) scale số pod dựa trên CPU, memory hoặc custom metrics như RPS hay độ dài hàng đợi."* |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Latency**: Agent v2 có thêm bước `search_knowledge_base` (~20 ms) và prompt dài hơn nên `p95` latency trong eval tăng nhẹ từ `188.8 ms` (v1) lên `221.8 ms` / `219.7 ms` (v2) — tức chậm hơn ~31 ms nhưng vẫn nằm rất xa dưới ngưỡng SLO `500 ms`.
- **Token & Chi phí**: Vì nhúng thêm đoạn tài liệu RAG vào prompt, số token trung bình mỗi câu của v2 tăng gấp đôi (`56.7` → `113.7 tokens/câu`), làm tổng chi phí cho 23 câu tăng từ `$0.000399` lên `$0.000790`.
- **Hiệu quả kinh tế thực chất (`Cost / câu đúng`)**: Agent v1 tuy rẻ mỗi lần gọi nhưng trả lời sai gần hết (chỉ đúng `1/23` câu = `4.3%`), nên chi phí để có **1 câu trả lời đúng** của v1 lên tới **`$0.00039855`**. Ngược lại, v2 (sau khi sửa KB) đúng `23/23` câu (`100%`), giúp **`Cost / câu đúng` giảm xuống chỉ còn `$0.00003436` — rẻ hơn gấp ~11.6 lần so với v1**!
- **Cơ chế Quality Gate trong CI**: Script `eval/run_eval.py` trả về `sys.exit(0)` khi `accuracy >= min_accuracy` và `regressions == 0`, ngược lại trả về **`exit code 1`**. Trong GitHub Actions (`.github/workflows/eval.yml`), khi step chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85 --baseline reports/eval_v2.json` nhận exit code `1`, workflow sẽ lập tức bị đánh dấu **Failed** và chặn không cho merge Pull Request.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [`screenshots/grafana-dashboard.png`](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing**: [`screenshots/prometheus-alert-firing.png`](screenshots/prometheus-alert-firing.png)

**Trả lời câu hỏi Exercise 7.4 (Đọc dashboard Grafana & Nginx):**
1. **`p95` và `avg` đang là bao nhiêu? Khoảng cách giữa chúng nói lên điều gì?**
   - Ở tải chuẩn 30 users (`MOCK_SLOW_RATE=0.03`), `avg` chỉ quanh mức `~220–240 ms` trong khi `p95` ~`400–480 ms` và `p99` vọt lên `~1.70 s` (khi bật fault injection `MOCK_SLOW_RATE=0.3`, `p95` trên Grafana nhảy lên `1.90 s` màu đỏ trong khi `p50` vẫn ở `~200 ms`). Khoảng cách lớn giữa `avg`/`p50` và `p95`/`p99` chứng tỏ phân phối độ trễ bị lệch phải mạnh (heavy-tailed latency distribution): đa số request rất nhanh nhưng một tỷ lệ nhỏ request bị nghẽn ở bước gọi LLM làm kéo dài đuôi phân phối.
2. **Panel "Requests/s theo instance": Nginx có chia đều traffic cho các instance không?**
   - Có. Trên panel *"Requests/s theo instance"*, hai đường biểu diễn lưu lượng của 2 instance (`172.21.0.5:8000` và `172.21.0.9:8000`, mỗi bên `~5.5–7.5 req/s`) bám sát và chồng khít lên nhau nhờ thuật toán **Round-Robin** cùng cơ chế phân giải DNS động (`resolver 127.0.0.11 valid=10s; server agent:8000 resolve`) của Nginx.
3. **Vì sao `input tokens/s` lớn hơn `output tokens/s`?**
   - Ở `AGENT_VERSION=v2` (RAG), mỗi câu hỏi đều được ghép thêm `SYSTEM_PROMPT` và đoạn tài liệu `context` lấy từ `KNOWLEDGE_BASE` trước khi gửi vào LLM (`input_tokens` trung bình `~109–114 tokens/câu`), trong khi câu trả lời ngắn gọn của agent chỉ dài khoảng `~45–55 tokens/câu`. Vì vậy tốc độ tiêu thụ `input tokens/s` luôn cao gấp ~2 lần `output tokens/s`.
4. **`curl http://localhost:8080/metrics` trả về gì? Vì sao?**
   - Trả về **`HTTP 404 Not Found`**. Lý do: Trong `nginx/nginx.conf` có cấu hình `location = /metrics { return 404; }` để **chặn không cho bên ngoài Internet đọc trộm số liệu nội bộ** (tên model, phiên bản, lưu lượng, chi phí, cấu trúc route). Chỉ có Prometheus nằm bên trong mạng Docker nội bộ `obs_net` mới scrape trực tiếp `http://agent:8000/metrics` qua Docker DNS service discovery (`dns_sd_configs`).

### 4.2 Thí nghiệm "phá hệ thống"

Unit test cho bộ quy tắc cảnh báo bằng `promtool`:
```text
$ docker run --rm -v "${PWD}/prometheus:/p" --entrypoint promtool prom/prometheus:v3.16.0 test rules /p/alert_rules_test.yml
Processing test file: /p/alert_rules_test.yml
  SUCCESS
```

Kết quả thực nghiệm Fault Injection (theo dõi thời gian từ thời điểm áp dụng thay đổi `T0 = 12:16:11 UTC` đến khi Prometheus chuyển trạng thái `pending` → `firing`):

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | **`AgentHighErrorRate`** (`severity: critical`, ngưỡng `> 5%`, `for: 1m`) | **~75 giây** (`1 phút 15 giây`: `activeAt = 12:16:17` → `firing = 12:17:26`; gồm ~15s cửa sổ `rate([1m])` vượt 5% + 60s `for: 1m`) | Panel **Error rate** (đỏ rực ở `19.68%`), **Requests/s theo status code** (đường `503` tăng vọt) và **LLM calls theo kết quả** (`error`). |
| B | `MOCK_SLOW_RATE=0.3` | **`AgentHighLatencyP95`** (`severity: warning`, ngưỡng `p95 > 1s`, `for: 2m`) | **~135 giây** (`2 phút 15 giây`: `activeAt = 12:16:17` → `firing = 12:18:26`; gồm ~15s để bucket histogram vượt 1s + 120s `for: 2m`) | Panel **Latency p95** (đỏ rực ở `1.90 s`), **Latency /ask — p50 / p95 / p99** và **LLM latency p95 theo model**. |
| C | `LLM_MODEL=mock-llm-large` | **`LLMCostBurnRateHigh`** (`severity: warning`, ngưỡng `> $2/giờ`, `for: 2m`) | **~145 giây** (`~2 phút 25 giây` ở tải ≥ 30 users: tốc độ đốt tiền nhảy lên **`$3.31/giờ`** > `$2/giờ` và giữ liên tục qua 120s `for: 2m`) | Panel **Cost burn rate (USD/giờ)** và **LLM cost (1h)** (chuyển sang màu cam/đỏ khi chi phí tăng ~16.7 lần, latency tăng 2.5 lần). *(Lưu ý: Sau khi nghiệm thu xong Thí nghiệm C, cấu hình được trả về model mặc định để chạy tiếp Thí nghiệm A+B+D nên trong ảnh chụp tổng hợp `prometheus-alert-firing.png` có 3 alert nhóm `agent-slo` đang `FIRING` còn `LLMCostBurnRateHigh` đã hạ về `INACTIVE`).* |
| D | `docker pause` 1 instance (`agent-3`) | **`AgentInstanceDown`** (`severity: critical`, biểu thức `up{job="agent"} == 0`, `for: 30s`) | **~40 giây** (`activeAt = 12:16:12` → `firing = 12:16:51`; gồm ≤10s chu kỳ scrape timeout + 30s `for: 30s`) | Panel **Instances up** (giảm từ `3` xuống `2`) và **Requests/s theo instance** (1 instance rơi về 0). *(Lưu ý: dùng `docker pause` thay vì `docker stop` để container vẫn còn trong Docker DNS nhưng không phản hồi scrape → `up == 0`; các lỗi `504 Gateway Timeout` nếu xảy ra ở Nginx không hiện trên metric của agent vì request chưa được agent xử lý xong).* |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** (`0 alerts`) | **∞ (Không bao giờ firing)** | Panel **Retrieval hit ratio (agent v2)** rơi từ `100%` về `0%`, **Tokens/s** giảm một nửa (`113.7` → `56.7 tokens/câu`), bảng version đổi sang `v1`, còn các panel Golden Signals (Error rate, Latency p95) đều **xanh tốt hơn cả v2**. |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

- Sự cố ở thí nghiệm E là **suy giảm chất lượng câu trả lời (silent quality regression)** chứ không phải lỗi hạ tầng: HTTP status vẫn trả `200 OK`, latency thậm chí còn nhanh hơn và tốn ít token hơn (do mất bước RAG retrieval). Vì vậy các alert hạ tầng dựa trên 4 Golden Signals (Latency, Traffic, Errors, Saturation) hoàn toàn "mù" trước lỗi này.
- Để phát hiện và chặn loại sự cố này trong production, cần kết hợp **3 lớp bảo vệ**:
  1. **Trước khi deploy (CI/CD Quality Gate)**: Chạy tự động bộ `eval/run_eval.py` trên **Golden Dataset** trong pipeline CI mỗi khi đổi code/prompt/config (`AGENT_VERSION`). Nếu `accuracy < 85%` hoặc có câu bị regression so với baseline, script trả `exit code 1` để chặn merge/deploy ngay từ đầu.
  2. **Giám sát Business / RAG Metric đặc thù trên Prometheus**: Đặt alert trên chính metric nghiệp vụ của pipeline RAG (`agent_retrieval_total` trong `app/metrics.py`), ví dụ cảnh báo khi **Retrieval Hit Ratio** (`sum(rate(agent_retrieval_total{result="hit"}[5m])) / sum(rate(agent_retrieval_total[5m]))`) đột ngột tụt xuống `< 50%` (hoặc bằng `0` khi không có metric retrieval nào được ghi nhận ở `v1`) hay khi số `input_tokens` trung bình mỗi request giảm bất thường.
  3. **Online Eval & User Feedback trên Traffic thật**: Lấy mẫu ngẫu nhiên (sampling 1–5%) các cặp hỏi–đáp thực tế trên production để chấm điểm ngầm bằng **LLM-as-a-Judge** (relevance, faithfulness/hallucination rate) kết hợp theo dõi tỉ lệ bấm 👎 (thumbs-down) của người dùng.

### 4.3 Debug bằng trace

> **Ghi chú môi trường:** Trên máy host Windows chạy Docker Compose có biến môi trường `LLM_MODEL=qwen2.5:3b` nên `docker-compose.yml` (`LLM_MODEL: ${LLM_MODEL:-mock-llm-small}`) truyền nhãn `qwen2.5:3b` vào container; hàm `call_llm` trong `utils/mock_llm.py` tự động ánh xạ tên model này về cấu hình hiệu năng và bảng giá chuẩn của `DEFAULT_MODEL` (`mock-llm-small`).

**1. Trace chậm nhất tìm được trong Jaeger ([`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png)):**

- `trace_id`: `0cc48e1f6f2a156f6216a75b6ef367ba`
- Tổng thời gian (`POST /ask`): **`1731.41 ms`** (`1.73 s`)
  - Span `agent.run`: `1726.28 ms` (`99.70%`)
  - Span `agent.retrieve_context`: `26.71 ms` (`1.54%`)
- **Span chiếm nhiều thời gian nhất**: **`chat qwen2.5:3b`** — **`1699.35 ms`** (chiếm **`98.15%`** tổng thời gian request; tags: `gen_ai.request.model = qwen2.5:3b`, `gen_ai.usage.input_tokens = 95`, `gen_ai.usage.output_tokens = 55`). Điều này chứng minh nguyên nhân gây chậm nằm ở bước gọi upstream LLM (dính tail latency `MOCK_SLOW_MS = 1500 ms`), không phải do bước tìm kiếm tài liệu RAG hay overhead của FastAPI.
- Dòng log JSON tương ứng (grep từ `docker compose -p k5-day14-observability logs agent` theo `trace_id`):

```json
{"ts": "2026-11-25T11:46:31.407687+00:00", "level": "INFO", "service": "observable-agent", "instance": "3a9599ab5030", "event": "llm_call", "trace_id": "0cc48e1f6f2a156f6216a75b6ef367ba", "span_id": "db37413603ccf6d6", "request_id": "fc7ca0f328a5", "model": "qwen2.5:3b", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1699.0}
```

**2. Trace lỗi tìm được trong Jaeger ([`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png)):**

- `trace_id`: `be3147bf0aef6f9c260f8d038565cf3f`
- Tổng thời gian (`POST /ask`, status `503`): **`869.85 ms`** (span `agent.retrieve_context`: `21.99 ms`, span `chat qwen2.5:3b`: `842.36 ms` có tag `error=true` và event `exception`: `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)`).
- Dòng log JSON tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T11:46:33.646445+00:00", "level": "INFO", "service": "observable-agent", "instance": "3a9599ab5030", "event": "llm_error", "trace_id": "be3147bf0aef6f9c260f8d038565cf3f", "span_id": "9f36a0975b60c570", "request_id": "fe827b2b3038", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu trích xuất trực tiếp từ hai file [`benchmark-results/scale_1_stats.csv`](benchmark-results/scale_1_stats.csv) và [`benchmark-results/scale_3_stats.csv`](benchmark-results/scale_3_stats.csv):

| Số instance | Endpoint / Dòng CSV | Tổng Requests | RPS (`Requests/s`) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|---|---|
| **1** (`scale_1`) | `POST /ask` | 7006 | **58.94** | **200** | **430** | **1700** | **91** (`1.30%`) |
| **1** (`scale_1`) | `Aggregated` (`/ask` + `/health`) | 7698 | **64.76** | **200** | **400** | **1700** | **91** (`1.18%`) |
| **3** (`scale_3`) | `POST /ask` | 7015 | **59.06** | **200** | **540** | **1700** | **70** (`1.00%`) |
| **3** (`scale_3`) | `Aggregated` (`/ask` + `/health`) | 7741 | **65.18** | **200** | **480** | **1700** | **70** (`0.90%`) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Kết quả quan sát được**: Khi scale từ 1 instance lên 3 instances với cùng mức tải `100 Locust users` (có thời gian nghỉ `wait_time = between(1.0, 2.0)` giây giữa các request trong `locustfile.py`), thông lượng tổng (`RPS` ~`64.76` vs `65.18 req/s`) và các phân vị độ trễ (`p50 = 200 ms`, `p95` ~`400–480 ms`, `p99 = 1700 ms`) **gần như không thay đổi**.
- **Vì sao scale từ 1 lên 3 không làm giảm p95/p99 và nút thắt nằm ở đâu?**
  1. **Nút thắt chính nằm ở độ trễ nội tại của Upstream LLM và bước Retrieval (I/O-bound latency, không phải CPU-bound ở tầng Agent)**: Mỗi request tới `/ask` bản chất chỉ là các lệnh chờ bất đồng bộ (`await asyncio.sleep()` mô phỏng ~20 ms retrieval + ~150–200 ms gọi LLM API, cùng 3% xác suất dính `MOCK_SLOW_MS = 1500 ms`). Ngay cả khi chạy 1 container `agent`, event loop `asyncio` của Uvicorn hoàn toàn chưa bị bão hòa CPU ở mức ~65 req/s, nên việc thêm 2 container nữa không thể làm cho API của LLM trả lời nhanh hơn.
  2. **Giới hạn thông lượng từ phía Client (Locust Wait Time)**: Theo định luật Little, với $N = 100$ users, thời gian nghỉ trung bình giữa 2 lần hỏi là $W_{\text{think}} = 1.5\text{ s}$ và thời gian xử lý trung bình $W_{\text{resp}} \approx 0.24\text{ s}$, thông lượng tối đa mà 100 Locust users tạo ra bị chặn trên bởi:
     $$\text{RPS}_{\max} = \frac{N}{W_{\text{think}} + W_{\text{resp}}} \approx \frac{100}{1.5 + 0.24} \approx 57.5 \text{ – } 65 \text{ req/s}$$
  3. **Khi nào scale ngang mới phát huy tác dụng?** Scale lên 3 instances giúp tăng **khả năng chịu lỗi (High Availability)** khi 1 instance gặp sự cố và chỉ giúp giảm latency/tăng RPS khi bản thân tiến trình Python/CPU của 1 instance bị bão hòa (ví dụ khi có xử lý CPU-bound nặng như tiền xử lý tài liệu, reranking cục bộ, hoặc khi lượng kết nối đồng thời vượt quá khả năng xử lý của 1 event loop đơn lẻ). Muốn giảm `p95`/`p99` của bước LLM, giải pháp phải là **semantic caching (Redis)**, **streaming response**, **timeout + retry/fallback sang model nhỏ hơn**, hoặc tối ưu độ dài prompt.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Không bao giờ đánh giá hiệu năng và đặt SLO theo độ trễ trung bình (`average`)**: Chỉ cần 3%–10% request bị chậm (tail latency), người dùng đã gặp trải nghiệm rất tệ (`p99 ≈ 1.7s`), nhưng `average` vẫn làm mượt con số xuống ~220–320 ms. Mọi SLO về độ trễ bắt buộc phải đặt trên phân vị cao (`p95`, `p99`).
  2. **Hạ tầng xanh không đồng nghĩa với AI Agent trả lời đúng**: Như đã chứng minh ở Thí nghiệm E (`AGENT_VERSION=v1`), khi RAG bị hỏng, mọi chỉ số hạ tầng (Latency, Error rate, CPU/RAM, Cost) đều đẹp hơn, không có bất kỳ alert Prometheus nào kêu. Vì vậy hệ thống AI bắt buộc phải có **Offline Eval (Golden Dataset + CI Quality Gate)** đi kèm **metrics chất lượng (`Cost / câu đúng`, `Retrieval Hit Ratio`)**.
  3. **Sức mạnh của sự liên kết 3 trụ cột (Metrics → Traces → Logs qua `trace_id`) và kiểm soát Cardinality**: Metrics trên Grafana giúp phát hiện *"đang có vấn đề"* (p95 hoặc error rate tăng), Jaeger Traces giúp khoanh vùng *"chậm hoặc lỗi ở span nào"* (`chat qwen2.5:3b` chiếm 98.15% thời gian), và `trace_id` trong JSON Log giúp truy ngược ra đúng bản ghi sự kiện chi tiết; đồng thời mọi label trong Prometheus phải dùng tập giá trị hữu hạn (`route.path` thay vì URL thô hay `user_id`) để tránh nổ cardinality làm tràn RAM.
- **Nếu đưa agent này lên production thật, các metric / alert sẽ bổ sung thêm:**
  - **Metrics bổ sung**:
    - `agent_retrieval_hit_ratio` & `agent_retrieval_top_score` (Histogram điểm tương đồng cosine của vector search để phát hiện drift dữ liệu).
    - `llm_time_to_first_token_seconds` (**TTFT**) và `llm_tokens_per_second` (nếu dùng streaming).
    - `agent_rate_limit_rejected_total` (đếm số lần trả `429`) và `agent_budget_rejected_total` (đếm số lần trả `402`) để theo dõi tần suất người dùng chạm ngưỡng bảo vệ.
    - `nginx_http_response_count_total{status="502|504"}` (metric ở tầng Load Balancer / Ingress để bắt được các lỗi timeout mà request chưa tới được tầng agent).
  - **Alerts bổ sung**:
    - `AgentRetrievalHitRateLow`: Cảnh báo khi tỉ lệ tìm thấy tài liệu RAG (`retrieval_hit_ratio`) tụt xuống `< 60%` trong `5m` (bắt ngay lỗi kiểu Thí nghiệm E).
    - `Gateway5xxSpike`: Cảnh báo ở tầng Nginx/Cloud Load Balancer khi có lỗi `502 Bad Gateway` / `504 Gateway Timeout`.
    - `DailyBudgetNearLimit`: Cảnh báo sớm ở mức `80%` ngân sách ngày (`DAILY_BUDGET_USD`) để chủ động xử lý trước khi người dùng bị chặn bởi lỗi `402`.
