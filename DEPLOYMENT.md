# Deployment Information

## Public URL
https://agent-production-466b9fdb.up.railway.app

## Platform
Railway

## Test Commands

### 1. Health Check (Liveness)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://agent-production-466b9fdb.up.railway.app/health"
# Expected: 200
curl "https://agent-production-466b9fdb.up.railway.app/health"
# Expected: {"status":"ok","uptime_seconds":...,"environment":"production"}
```

### 2. Readiness Check (Redis Connectivity)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://agent-production-466b9fdb.up.railway.app/ready"
# Expected: 200
curl "https://agent-production-466b9fdb.up.railway.app/ready"
# Expected: {"status":"ready"}
```

### 3. API Authentication Check (Without API Key -> 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://agent-production-466b9fdb.up.railway.app/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Expected: 401
```

### 4. API Test (With Valid `X-API-Key` -> 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://agent-production-466b9fdb.up.railway.app/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Expected: 200
```

## Environment Variables Set
- `PORT` (Platform injected / `8000`)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (Internal Redis connection URL on platform)
- `AGENT_API_KEY` (Secret key set in platform environment variables)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
