# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

1. **Hardcoded Secrets (Dòng 17–18)**:
   - **Vấn đề trong `develop/app.py`**: `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` được ghi cứng trực tiếp trong mã nguồn. Khi push code lên GitHub, toàn bộ khóa API và mật khẩu cơ sở dữ liệu sẽ bị lộ ngay trong lịch sử commit.
   - **Cách `production` đã sửa**: Trong `01-localhost-vs-production/production/config.py` (dòng 27, 32), các khóa bảo mật được đọc từ biến môi trường thông qua `os.getenv("OPENAI_API_KEY", "")` và `os.getenv("AGENT_API_KEY", "")`, kèm hàm `validate()` (dòng 37–46) bắt buộc phải có `AGENT_API_KEY` khi `ENVIRONMENT=production`.

2. **Không có Config Management & bật cứng Debug (Dòng 21–22)**:
   - **Vấn đề trong `develop/app.py`**: `DEBUG = True` và `MAX_TOKENS = 500` được gán cố định trong code, khiến ứng dụng không thể thay đổi cấu hình linh hoạt giữa các môi trường (`development`, `staging`, `production`) mà không sửa code.
   - **Cách `production` đã sửa**: Gom toàn bộ cấu hình vào dataclass `Settings` trong `production/config.py` (dòng 15–36), đọc từ biến môi trường với giá trị mặc định an toàn (`DEBUG=false`, `ENVIRONMENT=development`), kèm file mẫu `.env.example`.

3. **Dùng `print()` thay vì Structured Logging và in Secret ra Log (Dòng 33–34, 38)**:
   - **Vấn đề trong `develop/app.py`**: Sử dụng `print()` không có timestamp, log level hay cấu trúc chuẩn để parse. Nguy hiểm hơn, dòng 34 `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` in thẳng API key ra stdout/log.
   - **Cách `production` đã sửa**: Trong `production/app.py` (dòng 28–32, 49–55, 111–122), sử dụng thư viện `logging` với định dạng **Structured JSON** (`{"time":..., "level":..., "msg":...}`) và `json.dumps(...)`, chỉ ghi nhận các metadata an toàn (`question_length`, `client_ip`, `response_length`), tuyệt đối không log secret.

4. **Thiếu Health Check & Readiness Endpoints (Dòng 42–43)**:
   - **Vấn đề trong `develop/app.py`**: Không có endpoint `/health` hay `/ready`. Khi triển khai lên cloud hoặc container orchestrator (Railway, Render, Kubernetes), nền tảng không biết được container còn sống hay bị treo để tự động restart, cũng như không biết lúc nào app sẵn sàng nhận traffic.
   - **Cách `production` đã sửa**: Trong `production/app.py`, bổ sung `GET /health` (liveness probe, dòng 135–149), `GET /ready` (readiness probe trả `503` khi `not is_ready`, dòng 152–161) và `GET /metrics` (dòng 164–173).

5. **Không xử lý Graceful Shutdown**:
   - **Vấn đề trong `develop/app.py`**: Không quản lý vòng đời ứng dụng và không xử lý tín hiệu `SIGTERM`. Khi hệ thống deploy bản mới hoặc scale down, container bị tắt đột ngột làm đứt ngang các request đang xử lý dở.
   - **Cách `production` đã sửa**: Trong `production/app.py`, sử dụng `lifespan` context manager (dòng 40–67) để đánh dấu `is_ready = False` khi tắt và chờ request đang chạy hoàn tất, đồng thời đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 180–189).

6. **Bind `host="localhost"`, cố định `port=8000` và bật `reload=True` (Dòng 49–54)**:
   - **Vấn đề trong `develop/app.py`**: `host="localhost"` chỉ lắng nghe loopback bên trong máy/container nên khi chạy trong Docker sẽ không nhận được kết nối từ bên ngoài; `port=8000` cố định sẽ lỗi trên Railway/Render (nơi cấp port động qua biến `PORT`); `reload=True` chạy file watcher tốn tài nguyên và không an toàn trên production.
   - **Cách `production` đã sửa**: Trong `production/app.py` (dòng 194–199) và `production/config.py` (dòng 17–19), bind `host="0.0.0.0"`, đọc `port` từ biến môi trường `PORT`, và chỉ bật `reload=settings.debug`.

---

### Exercise 1.2: Run and test `develop` version

Lệnh gọi bản `develop` (nhận `question` qua query parameter theo Lưu ý K5 số 3):
```bash
curl -i -X POST "http://localhost:8000/ask?question=Hello"
```

Kết quả trả về từ server `develop`:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 07:57:09 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

Log trên terminal của server `develop` (lộ `OPENAI_API_KEY` ra stdout):
```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.
INFO:     127.0.0.1:54276 - "POST /ask?question=Hello HTTP/1.1" 200 OK
```

Kết quả khi chạy thử bản `production` (`GET /health`, `GET /ready`, `POST /ask`):
```http
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok","uptime_seconds":0.4,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T07:57:12.410578+00:00"}

HTTP/1.1 200 OK
content-type: application/json

{"ready":true}

HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"qwen2.5:3b"}
```

---

### Exercise 1.3: Comparison table (`develop` vs `production`)

| Feature | Basic (`develop/app.py`) | Advanced (`production/app.py` & `config.py`) | Tại sao quan trọng? |
|---------|--------------------------|-----------------------------------------------|---------------------|
| **Config** | Hardcode trực tiếp trong code (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG = True`, `port=8000`) | Đọc từ biến môi trường (`os.getenv`) qua `Settings` class (`config.py`), có `.env.example` và `validate()` fail-fast | Tuân thủ nguyên lý **12-Factor App**: tách biệt hoàn toàn config khỏi code, giúp đổi cấu hình giữa dev/staging/prod mà không sửa code và ngăn chặn rò rỉ secret lên Git. |
| **Health check** | ❌ Không có (`/health` và `/ready` đều không tồn tại) | ✅ Có `GET /health` (liveness), `GET /ready` (readiness trả `503` khi chưa sẵn sàng) và `GET /metrics` | Giúp cloud platform / orchestrator biết container còn sống không để tự restart khi treo (`/health`), và giúp load balancer chỉ điều hướng traffic vào instance đã khởi tạo xong (`/ready`). |
| **Logging** | Dùng `print()` xuất chuỗi tự do, in cả `OPENAI_API_KEY` ra màn hình | Dùng module `logging` xuất **Structured JSON** (`time`, `level`, `msg`, `event`), không ghi thông tin nhạy cảm | Log JSON có cấu trúc giúp các hệ thống log tập trung (ELK, Loki, Datadog, Cloud Logging) dễ dàng parse, index, tìm kiếm và tạo alert tự động; việc ẩn secret đảm bảo an toàn bảo mật. |
| **Shutdown** | Tắt đột ngột khi process bị dừng, không xử lý tín hiệu hệ thống | **Graceful shutdown**: bắt tín hiệu `SIGTERM` (`signal.signal`) kết hợp `lifespan` của FastAPI (`is_ready = False`, chờ request đang chạy hoàn tất) | Tránh làm rớt các request đang xử lý dở khi deploy phiên bản mới (rolling update) hoặc khi scale down, đảm bảo không mất dữ liệu và không trả lỗi 502/504 cho người dùng. |
| **Network & Binding** | `host="localhost"`, `port=8000` cố định, `reload=True` luôn bật | `host="0.0.0.0"`, `port` đọc động từ biến `PORT`, `reload` chỉ bật khi `DEBUG=true`, cấu hình CORS middleware | Trong container và cloud (Railway/Render/Cloud Run), app bắt buộc phải bind `0.0.0.0` và lắng nghe trên biến `PORT` do nền tảng cấp thì reverse proxy bên ngoài mới kết nối vào được. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image là gì?**
   - Base image là `python:3.11` (dòng 8: `FROM python:3.11`). Đây là image Debian đầy đủ đi kèm Python 3.11 và rất nhiều gói hệ thống/compilers (~1 GB+), dẫn đến kích thước image cuối rất lớn.
2. **Working directory là gì?**
   - Working directory bên trong container là `/app` (dòng 11: `WORKDIR /app`). Mọi lệnh `COPY`, `RUN`, `CMD` phía sau đều thực thi tương đối tại thư mục `/app` này.
3. **Tại sao `COPY requirements.txt` đứng trước `COPY . .` (hoặc `COPY app.py`)?**
   - Để tận dụng cơ chế **Docker layer caching**. Docker build từng lệnh thành một layer bất biến và cache lại. Vì code (`app.py`) thay đổi rất thường xuyên còn danh sách thư viện (`requirements.txt`) ít thay đổi hơn nhiều, việc copy `requirements.txt` và chạy `pip install` trước giúp Docker tái sử dụng cache của layer cài thư viện mỗi khi chỉ sửa code, giảm thời gian build từ vài phút xuống chỉ còn vài giây.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` khai báo lệnh mặc định (hoặc tham số mặc định cho `ENTRYPOINT`) khi khởi chạy container và **dễ dàng bị ghi đè** toàn bộ nếu truyền lệnh mới ở cuối `docker run <image> <other_cmd>`.
   - `ENTRYPOINT` định nghĩa chương trình thực thi cố định của container (khó bị ghi đè hơn, phải dùng cờ `--entrypoint`); mọi đối số truyền thêm trong `docker run` sẽ được nối vào làm tham số cho `ENTRYPOINT`.

---

### Exercise 2.2: Build and run `my-agent:develop`

Lệnh build từ gốc repo và chạy container:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --rm --name test-agent-dev -p 8000:8000 my-agent:develop
curl -i "http://localhost:8000/health"
curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"
```

Kết quả gọi container `my-agent:develop`:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:19:35 GMT
server: uvicorn
content-length: 53
content-type: application/json

{"status":"ok","uptime_seconds":2.5,"container":true}

HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:19:35 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

### Exercise 2.3: Multi-stage build & Image size comparison (`02-docker/production/Dockerfile`)

- **Stage 1 (`FROM python:3.11-slim AS builder`) làm gì?**
  - Cài đặt trình biên dịch và các thư viện build hệ thống (`gcc`, `libpq-dev`), sau đó chạy `pip install --no-cache-dir --user -r requirements.txt` để biên dịch và cài đặt toàn bộ Python packages vào `/root/.local`.
- **Stage 2 (`FROM python:3.11-slim AS runtime`) làm gì?**
  - Bắt đầu từ một image `python:3.11-slim` mới tinh, tạo user non-root (`appuser`), chỉ copy thư mục thư viện đã cài đặt (`/root/.local` -> `/home/appuser/.local`) từ stage `builder` cùng mã nguồn ứng dụng (`main.py`, `utils/mock_llm.py`), thiết lập `USER appuser`, `HEALTHCHECK` và khởi chạy `uvicorn` với 2 workers.
- **Tại sao image nhỏ hơn nhiều?**
  - Vì dùng base image `python:3.11-slim` thay vì `python:3.11` đầy đủ, đồng thời toàn bộ trình biên dịch nặng nề (`gcc`, `libpq-dev`, headers, apt cache, build artifacts) đều bị bỏ lại ở stage `builder`, không xuất hiện trong image `runtime` cuối cùng.

**Số đo kích thước image thực tế trên máy (`docker images my-agent` & `docker image inspect`):**

```text
REPOSITORY   TAG        IMAGE ID       SIZE
my-agent     advanced   6ffb63537645   240MB
my-agent     develop    fcfd865e9c05   1.67GB

[my-agent:develop]:  1,667,788,022 bytes (~1667.79 MB / 1.67 GB)
[my-agent:advanced]:   239,815,481 bytes (~239.82 MB)
```

- **Develop (`my-agent:develop`)**: `1667.79 MB` (`1.67 GB`)
- **Production (`my-agent:advanced`)**: `239.82 MB` (`240 MB`)
- **Chênh lệch (Reduction)**: Giảm `1427.97 MB`, tương đương nhỏ hơn **`85.62%`** so với bản develop.

---

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

**Sơ đồ kiến trúc các services và giao tiếp trong stack:**

```text
                        ┌──────────────────────────────────────────────────────┐
                        │           Docker Bridge Network: internal            │
                        │                                                      │
┌────────────┐  :80     │  ┌──────────────┐   proxy_pass    ┌───────────────┐  │
│   Client   │ ─────────┼─▶│    nginx     │ ───────────────▶│     agent     │  │
│ (curl/web) │  :443    │  │(nginx:alpine)│ http://agent:8000│(FastAPI :8000)│  │
└────────────┘          │  └──────────────┘                 └───────┬───────┘  │
                        │                                           │          │
                        │                         ┌─────────────────┴───────┐  │
                        │                         ▼                         ▼  │
                        │                 ┌───────────────┐         ┌───────────────┐
                        │                 │     redis     │         │    qdrant     │
                        │                 │(redis:7-alpine│         │(qdrant:v1.9.0)│
                        │                 │    :6379)     │         │  :6333/:6334  │
                        │                 └───────┬───────┘         └───────┬───────┘
                        └─────────────────────────┼─────────────────────────┼──────────┘
                                                  ▼                         ▼
                                         [Volume: redis_data]     [Volume: qdrant_data]
```

- **Các services được khởi chạy (4 services)**:
  1. `nginx` (`nginx:alpine`): Reverse proxy & load balancer duy nhất mở cổng ra host (`80:80`, `443:443`), áp dụng rate limit (`10r/s`, `burst=20`) và security headers (`X-Frame-Options`, `X-Content-Type-Options`).
  2. `agent` (build từ `02-docker/production/Dockerfile` target `runtime`): AI Agent chạy trên cổng nội bộ `8000/tcp` (không expose trực tiếp ra ngoài host), chỉ khởi động sau khi `redis` và `qdrant` đều đạt trạng thái `service_healthy`.
  3. `redis` (`redis:7-alpine`): Cache cho session và rate limiting ở cổng nội bộ `6379/tcp`, gắn persistent volume `redis_data`.
  4. `qdrant` (`qdrant/qdrant:v1.9.0`): Vector database cho RAG ở cổng nội bộ `6333/tcp`, gắn persistent volume `qdrant_data`.
- **Cách giao tiếp**: Tất cả 4 services cùng nằm trong mạng nội bộ `internal` (bridge network) và gọi nhau qua **Docker DNS bằng tên service** (`http://agent:8000`, `redis://redis:6379/0`, `http://qdrant:6333`).

**Kết quả trạng thái các container (`docker compose ps`) và test qua Nginx (`port 80`):**

```text
NAME                       IMAGE                   COMMAND                  SERVICE   STATUS                    PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   "uvicorn main:app --…"   agent     Up 16 seconds (healthy)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            "/docker-entrypoint.…"   nginx     Up 16 seconds             0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    "./entrypoint.sh"        qdrant    Up 26 seconds (healthy)   6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          "docker-entrypoint.s…"   redis     Up 27 seconds (healthy)   6379/tcp
```

Test `GET http://localhost/health` qua Nginx:
```http
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 08:21:14 GMT
Content-Type: application/json
Content-Length: 96
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":13.6,"version":"2.0.0","timestamp":"2026-11-25T08:21:14.703737"}
```

Test `POST http://localhost/ask` qua Nginx:
```http
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 08:21:14 GMT
Content-Type: application/json
Content-Length: 126
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1: Cloud Deployment of Part 6 Production Agent (`06-lab-complete/`)

- **Platform**: Railway
- **Public URL**: https://agent-production-466b9fdb.up.railway.app (xem chi tiết trong [DEPLOYMENT.md](DEPLOYMENT.md))
- **Screenshots**:
  - [Deployment dashboard](screenshots/dashboard.png)
  - [Service running](screenshots/running.png)
  - [Test results](screenshots/test.png)
- **Kết quả 4 lệnh tự kiểm tra ở CP6**:
  ```bash
  curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
  curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
  curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
  curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
  ```

---

### Exercise 3.2: So sánh `railway.toml` vs `render.yaml`

| Tiêu chí | `railway.toml` (Railway Config-as-Code) | `render.yaml` (Render Blueprint IaC) | Tại sao có sự khác biệt này? |
|---|---|---|---|
| **Phạm vi cấu hình (Scope)** | Chỉ cấu hình **cách build và deploy của 1 service đơn lẻ** (`[build]` builder = `DOCKERFILE`/`NIXPACKS`, `[deploy]` `startCommand`, `healthcheckPath = "/health"`, `restartPolicyType`). | Là một **Infrastructure-as-Code (IaC) Blueprint toàn diện** cho cả hệ thống: khai báo được danh sách nhiều `services` cùng lúc (cả Web Service `type: web` lẫn managed Redis `type: redis`, region, plan, persistent disk). | Railway quản lý multi-service (như tạo thêm Redis) và biến môi trường trực quan trên Project Canvas / CLI (`railway add`, `railway variables`), trong khi Render hướng tới mô hình khai báo toàn bộ stack hạ tầng trong một file YAML duy nhất để đồng bộ tự động từ Git. |
| **Quản lý Biến môi trường & Secrets** | **Không** khai báo biến môi trường hay secrets trong `railway.toml`; mọi biến được đặt qua Railway Dashboard hoặc CLI (`railway variables set AGENT_API_KEY=...`). | Khai báo trực tiếp danh sách `envVars` ngay trong `render.yaml`: biến thường gán `value`, secret dùng `generateValue: true` (tự sinh ngẫu nhiên) hoặc `sync: false` (nhập tay trên Dashboard, không lưu giá trị thật vào Git). | `render.yaml` đóng vai trò khuôn mẫu khởi tạo toàn bộ môi trường (Blueprint) nên cần biết danh sách các biến bắt buộc ngay trong file mà vẫn đảm bảo không lộ secret vào Git. |
| **Định dạng & Cơ chế Build** | Định dạng **TOML** ngắn gọn, ưu tiên zero-config (tự nhận diện `Dockerfile` hoặc `NIXPACKS`). | Định dạng **YAML** tường minh (`runtime: docker` hoặc `runtime: python`, chỉ định rõ `buildCommand`, `startCommand`, `autoDeploy`). | Railway tối ưu cho tốc độ deploy nhanh từ CLI (`railway up`), còn Render tối ưu cho GitOps CI/CD gắn chặt với nhánh GitHub. |

---

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

Đọc hai file `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD trên Google Cloud hoạt động qua **4 bước tuần tự** khi có commit push lên nhánh `main`:
1. **Step 1 — Test (`id: test`)**: Dùng container `python:3.11-slim` cài đặt `requirements.txt` và chạy bộ kiểm thử tự động `pytest tests/ -v --tb=short`; nếu bất kỳ test nào fail thì pipeline dừng ngay, không build image.
2. **Step 2 — Build Docker Image (`id: build`, `waitFor: [test]`)**: Dùng `gcr.io/cloud-builders/docker` để build image gắn 2 tag (`gcr.io/$PROJECT_ID/ai-agent:$COMMIT_SHA` để định danh chính xác bản build theo commit và `:latest`), đồng thời tận dụng `--cache-from` layer cache để tăng tốc.
3. **Step 3 — Push Image (`id: push`, `waitFor: [build]`)**: Đẩy toàn bộ các tag của Docker image vừa build lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Step 4 — Deploy lên Cloud Run (`id: deploy`, `waitFor: [push]`)**: Dùng `gcloud run deploy` (tương ứng cấu hình Knative trong `service.yaml`) để triển khai image `:$COMMIT_SHA` lên vùng `asia-southeast1` với cấu hình production: giới hạn tài nguyên (`1 CPU`, `512Mi RAM`, `containerConcurrency: 80`), auto-scaling từ `minScale: 1` (tránh cold start) đến `maxScale: 10`, nạp secret `OPENAI_API_KEY` / `AGENT_API_KEY` an toàn từ **Secret Manager** (`secretKeyRef`), và giám sát bằng `livenessProbe` (`/health`) cùng `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

1. **API key được check ở đâu?**
   - Được kiểm tra trong hàm dependency `verify_api_key(api_key: str = Security(api_key_header))` (dòng 39–54) sử dụng `APIKeyHeader(name="X-API-Key", auto_error=False)`, và được gắn vào endpoint `POST /ask` thông qua `_key: str = Depends(verify_api_key)` (dòng 70).
2. **Điều gì xảy ra nếu thiếu hoặc sai key?**
   - Nếu không gửi header `X-API-Key` (`not api_key`), server trả về **`HTTP 401 Unauthorized`** (`"Missing API key. Include header: X-API-Key: <your-key>"`).
   - Nếu gửi sai key (`api_key != API_KEY`), bản `04-api-gateway/develop/app.py` trả về **`HTTP 403 Forbidden`** (`"Invalid API key."`). *(Lưu ý: Trong hợp đồng của Part 6 `06-lab-complete`, cả thiếu và sai key đều yêu cầu trả `401`)*.
3. **Làm sao rotate key mà không gián đoạn dịch vụ (zero-downtime)?**
   - Không hardcode key trong code mà đọc danh sách key hợp lệ từ biến môi trường (ví dụ `AGENT_API_KEYS=new_key,old_key`) hoặc từ Redis / Secret Manager. Khi rotate: thêm `new_key` song song với `old_key` (dual-key window), cập nhật toàn bộ client sang `new_key`, theo dõi log đến khi không còn traffic nào dùng `old_key` thì thu hồi `old_key`.

**Kết quả test thực tế `curl -i` bản `develop` (`AGENT_API_KEY=secret-key-123`):**

- **Không có API key (`401 Unauthorized`)**:
```http
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 08:29:43 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

- **Sai API key (`403 Forbidden`)**:
```http
HTTP/1.1 403 Forbidden
date: Wed, 25 Nov 2026 08:29:43 GMT
server: uvicorn
content-length: 29
content-type: application/json

{"detail":"Invalid API key."}
```

- **Đúng API key (`200 OK`)**:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:29:43 GMT
server: uvicorn
content-length: 144
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

1. **Giải thích JWT Flow (`auth.py`)**:
   - Client gửi `username` / `password` tới `POST /auth/token`. Server xác thực qua `authenticate_user()` và gọi `create_token()` ký JWT bằng thuật toán `HS256` với `SECRET_KEY`, payload chứa `sub` (username), `role` (`user` hoặc `admin`), `iat` và `exp` (60 phút).
   - Ở các request tiếp theo tới `POST /ask`, client đính kèm header `Authorization: Bearer <token>`. Dependency `verify_token()` dùng `jwt.decode()` kiểm tra chữ ký số và hạn sử dụng (`exp`) một cách **stateless** mà không cần truy vấn database mỗi request.
2. **Câu hỏi Rate Limiting (`rate_limiter.py`)**:
   - **Algorithm nào được dùng?** **Sliding Window Log / Counter** (dùng `deque` lưu danh sách các timestamp request của từng `user_id` trong cửa sổ trượt 60 giây; mỗi khi có request mới sẽ `popleft()` toàn bộ timestamp nhỏ hơn `now - 60`).
   - **Limit là bao nhiêu requests/minute?** Với role `user` (`rate_limiter_user`, tài khoản `student`): **10 requests / 60 giây**. Với role `admin` (`rate_limiter_admin`, tài khoản `teacher`): **100 requests / 60 giây**.
   - **Làm sao phân biệt / nâng giới hạn cho `admin`?** Trong `app.py` (dòng 141), sau khi giải mã JWT lấy `role = user["role"]`, ứng dụng chọn instance rate limiter theo role: `limiter = rate_limiter_admin if role == "admin" else rate_limiter_user` (hoặc có thể bypass hoàn toàn nếu `role == "admin"`).

**Kết quả test thực tế `curl -i` bản `production` (đã che JWT token):**

- **1. Gọi `POST /ask` khi không có JWT token (`401 Unauthorized`)**:
```http
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 08:29:47 GMT
content-length: 81
content-type: application/json
www-authenticate: Bearer
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

- **2. Lấy JWT token tại `POST /auth/token` với tài khoản `student` / `demo123` (`200 OK`)**:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:29:47 GMT
content-length: 304
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"access_token":"<REDACTED_JWT_TOKEN>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."}
```

- **3. Vòng lặp gọi `POST /ask` với Bearer Token — Request #1 đến #10 thành công (`200 OK`), từ Request #11 bị chặn (`429 Too Many Requests`)**:

Request #1 (`200 OK`, `requests_remaining: 9`):
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:29:47 GMT
content-length: 222
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Test 1","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":2.5e-05}}
```

Request #10 (`200 OK`, `requests_remaining: 0`):
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:29:48 GMT
content-length: 224
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Test 10","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":0,"budget_remaining_usd":0.000249}}
```

Request #11 (`429 Too Many Requests` kèm header `Retry-After: 60`):
```http
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 08:29:48 GMT
content-length: 112
content-type: application/json
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795595448
retry-after: 60
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":60}}
```

---

### Exercise 4.4: Cost Guard Implementation & Tại sao cần cả Rate Limit lẫn Cost Guard

1. **Cách hoạt động và triển khai Cost Guard với Redis**:
   - **Trước khi gọi LLM (`check_budget`)**: Đọc tổng chi phí đã tiêu của user/hệ thống từ Redis key theo ngày hoặc tháng (ví dụ `cost:daily:2026-11-25` hoặc `budget:{user_id}:{YYYY-MM}`). Nếu `current_cost >= budget_usd`, lập tức chặn request và trả về **`HTTP 402 Payment Required`** mà không gọi tới LLM API.
   - **Sau khi gọi LLM (`record_cost`)**: Tính chi phí thực tế của request dựa trên số lượng input/output tokens:
     $$\text{cost} = \frac{\text{input\_tokens}}{1000} \times \text{PRICE\_INPUT\_PER\_1K} + \frac{\text{output\_tokens}}{1000} \times \text{PRICE\_OUTPUT\_PER\_1K}$$
     Sau đó cộng dồn nguyên tử (atomic) vào Redis bằng lệnh `INCRBYFLOAT` và đặt `EXPIRE` (TTL 24h cho daily budget hoặc 32 ngày cho monthly budget) để tự động reset sang chu kỳ mới.
   - **Code triển khai chuẩn với Redis**:
     ```python
     def check_budget() -> None:
         current = float(r.get("cost:total_usd") or 0.0)
         if current >= settings.daily_budget_usd:
             raise HTTPException(status_code=402, detail="Budget exceeded")

     def record_cost(input_tokens: int, output_tokens: int) -> float:
         cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
         r.incrbyfloat("cost:total_usd", cost)
         return cost
     ```

2. **Tại sao cần CẢ Rate Limit (429) lẫn Cost Guard (402)?**
   - **Rate Limit bảo vệ tốc độ (tài nguyên hạ tầng ngắn hạn)**: Chặn 1 user hoặc bot bắn hàng trăm request trong vài giây gây nghẽn CPU/connection pool hoặc chạm rate limit của upstream OpenAI/Anthropic. Tuy nhiên, nếu user gọi đều đặn 9 request/phút suốt 24 giờ với prompt rất dài (hàng chục nghìn tokens/request), họ không bao giờ vi phạm rate limit nhưng vẫn có thể đốt hàng trăm USD tiền LLM.
   - **Cost Guard bảo vệ ngân sách (tài chính dài hạn)**: Kiểm soát tổng số tiền token thực tế tiêu thụ theo ngày/tháng. Ngược lại, nếu chỉ có Cost Guard mà không có Rate Limit, kẻ tấn công có thể bắn 1.000 request đồng thời trong 1 giây làm sập server hoặc vượt ngân sách trước khi các request kịp ghi nhận cost. Do đó, production agent bắt buộc phải kết hợp cả hai lớp bảo vệ.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Liveness (`GET /health`) vs Readiness (`GET /ready`) (`05-scaling-reliability/develop/app.py`)

- **Liveness Probe (`GET /health`) — "Process còn sống không?"**:
  - Dùng để container orchestrator (Docker, Railway, Render, Kubernetes) kiểm tra xem tiến trình Python/Uvicorn của agent còn phản hồi hay đã bị deadlock/treo.
  - **Quan trọng**: `/health` phải **luôn trả về `200 OK`** miễn là process của agent còn sống, **kể cả khi Redis hay database tạm thời mất kết nối**. Nếu `/health` trả về `503` khi Redis chết, orchestrator sẽ liên tục kill và restart toàn bộ các agent containers (gây cascading failure / crash loop) trong khi việc restart agent không hề sửa được lỗi của Redis.
- **Readiness Probe (`GET /ready`) — "Instance đã sẵn sàng nhận traffic chưa?"**:
  - Dùng để Load Balancer / Reverse Proxy quyết định có điều phối request của người dùng vào instance này hay không.
  - `/ready` kiểm tra các phụ thuộc bên ngoài (như `r.ping()` tới Redis) và trạng thái khởi tạo/tắt (`_is_ready`). Khi Redis mất kết nối hoặc agent đang trong quá trình khởi động / graceful shutdown, `/ready` trả về **`503 Service Unavailable`** để Load Balancer tạm ngưng gửi request mới vào instance đó mà **không** kill container.

---

### Exercise 5.2: Graceful Shutdown

- **Cơ chế hoạt động**:
  1. Khi orchestrator muốn dừng container (deploy bản mới, scale down, hoặc chạy `docker stop`), nó gửi tín hiệu **`SIGTERM`** tới tiến trình PID 1 trong container và chờ một khoảng grace period (mặc định 10–30 giây) trước khi gửi `SIGKILL`.
  2. Khi nhận `SIGTERM`, agent lập tức chuyển trạng thái `_is_ready = False` (để `/ready` trả 503 và ngừng nhận request mới từ load balancer), đồng thời chờ các request đang xử lý dở (`_in_flight_requests > 0`) hoàn tất và trả response `200 OK` cho client.
  3. Trong giai đoạn shutdown của `lifespan`, ứng dụng đóng các kết nối Redis/DB sạch sẽ rồi thoát với **`exit code 0`**.
  4. **Lưu ý kỹ thuật với Uvicorn**: Uvicorn đã có sẵn signal handler cho `SIGTERM`. Nếu tự đăng ký `signal.signal(signal.SIGTERM, custom_handler)`, bắt buộc phải lưu lại handler cũ (`_prev = signal.getsignal(signal.SIGTERM)`) và gọi lại `_prev(signum, frame)` bên trong `custom_handler`; nếu không, Uvicorn sẽ không bao giờ nhận được tín hiệu dừng và bị treo cho tới khi bị `SIGKILL` (exit code 137).

---

### Exercise 5.3: Stateless Design — Tại sao state lưu trong RAM sẽ hỏng khi scale?

- Khi chạy **1 instance**, việc lưu `conversation_history = {}` hoặc bộ đếm rate limit trong RAM (biến toàn cục của Python) có vẻ hoạt động bình thường (nhưng nếu chạy `uvicorn --workers 2` ngay trong 1 container thì 2 worker processes cũng đã có 2 vùng nhớ RAM tách biệt!).
- Khi scale lên **3 instances** (`agent-1`, `agent-2`, `agent-3`) đứng sau Nginx Load Balancer (phân phối kiểu Round-Robin):
  - Request 1 của User A rơi vào `agent-1` → lịch sử hội thoại lưu trong RAM của `agent-1`.
  - Request 2 của cùng User A được Nginx chuyển sang `agent-2` → RAM của `agent-2` hoàn toàn trống đối với session này → Agent mất ngữ cảnh hội thoại (hoặc bộ đếm rate limit bị reset về 0 trên mỗi instance).
  - Nếu `agent-1` bị restart hoặc scale down, toàn bộ lịch sử trong RAM của nó biến mất vĩnh viễn.
- **Giải pháp Stateless**: Không lưu bất kỳ session state, rate limit counter hay cost budget nào trong RAM của process; toàn bộ state phải được đẩy xuống **external shared store là Redis** (`session:{session_id}`, `ratelimit:{key}`, `cost:total_usd`). Khi đó mọi worker và mọi instance đều đọc/ghi chung một nguồn dữ liệu thống nhất.

---

### Exercise 5.4 & 5.5: Load Balancing & Stateless Verification (`05-scaling-reliability/production/`)

Lệnh khởi chạy stack với 3 replicas của `agent`, 1 `redis` và 1 `nginx` load balancer (theo Lưu ý K5 số 7):
```bash
cd 05-scaling-reliability/production
touch .env.local
docker compose -p k5-day14-scaling up -d --build --scale agent=3
docker compose -p k5-day14-scaling ps
python test_stateless.py
docker compose -p k5-day14-scaling down -v
```

**Trạng thái các container trong stack (`docker compose -p k5-day14-scaling ps`):**
```text
NAME                       IMAGE                    COMMAND                  SERVICE   STATUS                    PORTS
k5-day14-scaling-agent-1   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     Up 14 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-2   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     Up 13 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-3   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     Up 14 seconds (healthy)   8000/tcp
k5-day14-scaling-nginx-1   nginx:alpine             "/docker-entrypoint.…"   nginx     Up 13 seconds             0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   redis:7-alpine           "docker-entrypoint.s…"   redis     Up 25 seconds (healthy)   6379/tcp
```

**Kết quả chạy thực tế `python test_stateless.py` (gọi `POST http://localhost:8080/chat` và `GET /chat/{session_id}/history`):**
```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: acb38582-ca83-460d-a5da-d40bb286c383

Request 1: [instance-f04313]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-51eaae]
  Q: Why do we need containers?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 3: [instance-ba87b6]
  Q: What is Kubernetes?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 4: [instance-f04313]
  Q: How does load balancing work?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 5: [instance-51eaae]
  Q: What is Redis used for?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-51eaae', 'instance-ba87b6', 'instance-f04313'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Kubernetes?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: How does load balancing work?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Redis used for?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...

✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:**
- Nginx Load Balancer (cổng `8080`) đã phân phối 5 request liên tiếp theo thuật toán **Round-Robin** qua cả 3 container instance khác nhau: `instance-f04313` (Req 1, 4), `instance-51eaae` (Req 2, 5) và `instance-ba87b6` (Req 3).
- Mặc dù mỗi lượt hỏi rơi vào một container khác nhau, cả 5 lượt hỏi–đáp (tổng cộng **10 messages**: 5 `user` + 5 `assistant`) của cùng `session_id = acb38582-ca83-460d-a5da-d40bb286c383` vẫn được bảo toàn nguyên vẹn khi gọi `GET /chat/{session_id}/history`, bởi vì mọi instance đều đọc và ghi session state chung tại khóa `session:acb38582-ca83-460d-a5da-d40bb286c383` trong **Redis**.

---

## Part 6: Final Project — `check_production_ready.py` Output (`PASS 12/12`)

Toàn bộ kết quả chạy `python check_production_ready.py` trong `06-lab-complete/` trên WSL2 + Docker:

```text
🔎 Kiểm tra /mnt/c/LONG/VinUni AI/Lab_day14/K5-L3A-DAY14-HoangNguyenLong-2A202603476-Deployment-Benchmark-Observability/06-lab-complete
  ⏳ Kiểm tra tĩnh: file, Dockerfile, compose, config, code...
  ⏳ Chuẩn bị Redis cho bài test stateless...
  ⏳ Khởi động agent: uvicorn app.main:app --workers 2 (Redis: container redis:7-alpine tạm thời)
  ⏳ Restart agent để kiểm tra stateless...
  ⏳ Kiểm tra readiness khi Redis mất kết nối...
  ⏳ Kiểm tra cost guard (budget ≈ 0)...
  ⏳ Kiểm tra graceful shutdown (SIGTERM)...
  ⏳ Build Docker image prod-check:0eaf4ad4 (Docker 29.9.2) — lần đầu có thể mất vài phút...

================================================================
  Production Readiness Check — Day 14 Lab
================================================================

✅ 1. Dockerfile (multi-stage, < 500 MB)
     ✅ Dockerfile tồn tại
     ✅ requirements.txt tồn tại
     ✅ Multi-stage build (≥ 2 lệnh FROM)
     ✅ Base image gọn (slim / alpine / distroless) — stage cuối dùng public.ecr.aws/docker/library/python:3.11-slim
     ✅ Chạy bằng user non-root
     ✅ Có HEALTHCHECK
     ✅ Docker: build image thành công — 71s
     ✅ Docker: image < 500 MB — 297 MB
     ✅ Docker: container chạy được, GET /health → 200

✅ 2. docker-compose.yml (agent + redis)
     ✅ docker-compose.yml tồn tại
     ✅ Có service agent (build từ Dockerfile) + redis — services: agent, redis — đọc bằng docker compose config
     ✅ Service agent kết nối redis (REDIS_URL + depends_on)

✅ 3. .dockerignore
     ✅ .dockerignore tồn tại và có nội dung
     ✅ .dockerignore loại trừ .env (secrets)
     ✅ .dockerignore loại trừ __pycache__, venv

✅ 4. Health check endpoint (GET /health)
     ✅ Code có route /health
     ✅ Khi chạy: GET /health → 200 — uvicorn --workers 2

✅ 5. Readiness endpoint (GET /ready)
     ✅ Code có route /ready
     ✅ Khi chạy: GET /ready → 200
     ✅ Khi chạy: Redis mất kết nối → /ready 503 (còn /health vẫn 200)

✅ 6. API Key authentication
     ✅ Code đọc header X-API-Key
     ✅ Khi chạy: thiếu / sai API key → 401
     ✅ Khi chạy: API key đúng → 200

✅ 7. Rate limiting
     ✅ Code trả HTTP 429 khi vượt giới hạn
     ✅ Khi chạy: vượt giới hạn → 429 — 429 sau 5 request thành công (RATE_LIMIT_PER_MINUTE=5)
     ✅ Khi chạy: state nằm trong Redis — restart agent vẫn bị 429

✅ 8. Cost guard
     ✅ Code trả HTTP 402 khi hết budget
     ✅ Khi chạy: hết budget → 402 — 402 ở request thứ 2

✅ 9. Config từ environment variables
     ✅ app/config.py đọc biến môi trường
     ✅ .env.example liệt kê đủ biến cấu hình
     ✅ .env nằm trong .gitignore
     ✅ Không hard-code secret trong code
     ✅ Khi chạy: agent dùng AGENT_API_KEY và RATE_LIMIT_PER_MINUTE từ env

✅ 10. Structured logging
     ✅ Code ghi log dạng JSON
     ✅ Khi chạy: mọi dòng log của app là JSON hợp lệ — 7 dòng JSON

✅ 11. Graceful shutdown
     ✅ Code xử lý SIGTERM / lifespan shutdown
     ✅ Khi chạy: SIGTERM lúc đang có request → request vẫn 200, process tự thoát — exit code 0
     ✅ Docker: `docker stop` tắt êm (exit code 0, < 10s) — exit code 0, 1.1s

✅ 12. Public URL ready (Railway / Render config)
     ✅ Có railway.toml hoặc render.yaml (không chỉ toàn comment)
     ✅ railway.toml: builder + healthcheckPath = "/health"
     ✅ render.yaml: web service + healthCheckPath /health
     ✅ render.yaml: secret không ghi thẳng giá trị (generateValue / sync: false)
     ✅ App lắng nghe theo biến PORT do platform cấp

================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log (Khai báo sử dụng AI theo `RULES.md`)

Theo mục 1 của `RULES.md`, dưới đây là nhật ký sử dụng AI hỗ trợ trong quá trình thực hiện bài lab:

1. **Tìm hiểu khái niệm & đối chiếu cấu hình (Part 1–5)**:
   - **Đã hỏi gì**: Hỏi về sự khác biệt bản chất giữa API Key và JWT Token, lý do `/health` không được phụ thuộc Redis trong khi `/ready` phải trả `503` khi mất kết nối Redis, và cách so sánh chi tiết `railway.toml` với `render.yaml` cũng như 4 bước trong `cloudbuild.yaml`.
   - **Nhận được gì**: Giải thích nguyên lý 12-Factor, cơ chế stateless JWT verification, cách tránh crash-loop khi tách biệt liveness/readiness probes, và cấu trúc IaC Blueprint của Render/Cloud Run.
   - **Tự sửa & tự kiểm tra thế nào**: Tự chạy thực tế từng app `develop` và `production` của Part 1, 2, 4, 5 trên máy cá nhân, đo dung lượng Docker image thật bằng `docker images` (`1.67 GB` vs `240 MB`), chạy vòng lặp `curl -i` thu thập mã `401 / 200 / 429` và kiểm chứng 3 replicas với `test_stateless.py`.

2. **Hoàn thiện các `TODO` của Final Project (`06-lab-complete/` — Part 6)**:
   - **Đã hỏi gì**: Gợi ý cách viết `JsonFormatter` cho `logging`, cách cài đặt Sliding Window Rate Limiter bằng Redis Sorted Set (`ZREMRANGEBYSCORE`, `ZCARD`, `ZADD`, `EXPIRE`), Cost Guard dùng `INCRBYFLOAT`, và cách nối signal handler `SIGTERM` mà không làm mất handler gốc của Uvicorn.
   - **Nhận được gì**: Cấu trúc code cho `app/config.py`, `app/redis_client.py`, `app/auth.py`, `app/rate_limiter.py`, `app/cost_guard.py`, `app/main.py` và multi-stage `Dockerfile` với non-root user.
   - **Tự sửa & tự kiểm tra thế nào**: Đổi base image sang mirror chính thức `public.ecr.aws/docker/library/python:3.11-slim` khi mạng bị Docker Hub giới hạn pull rate (`429 Too Many Requests`), cấu hình `PYTHONUSERBASE=/home/appuser/.local`, chạy `python check_production_ready.py` trong WSL2 đạt **`PASS 12/12` (43/43 checks passed)** và deploy thật lên Railway (`https://agent-production-466b9fdb.up.railway.app`) kiểm tra đủ 4 lệnh trả về `200 · 200 · 401 · 200`.

3. **Benchmark & Observability (Part 7)**:
   - **Đã hỏi gì**: Cách thêm metric Histogram `agent_question_length_chars`, bổ sung 2 mục tài liệu còn thiếu (`scaling-03` về Kubernetes HPA và `security-02` về JWT) vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`, và phân tích nguyên nhân vì sao scale từ 1 lên 3 replicas không làm giảm `p95` latency của bước gọi LLM.
   - **Nhận được gì**: Hai đoạn tài liệu chuẩn cho `KNOWLEDGE_BASE` và phân tích định luật Little / I/O-bound latency.
   - **Tự sửa & tự kiểm tra thế nào**: Chạy toàn bộ 7 lượt `load_test.py`, 3 lượt `run_eval.py` (đạt `100%` accuracy `23/23` không regression), chạy 2 lượt Locust headless (`scale_1` và `scale_3`), kích hoạt fault injection trên stack Docker Compose để quan sát 3–4 alerts chuyển sang `FIRING`, trích xuất `trace_id` thật từ Jaeger và đối chiếu khớp 100% mọi con số giữa `BENCHMARK_REPORT.md` và các file JSON/CSV.





