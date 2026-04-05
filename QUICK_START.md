# Quick Start Guide - Docker Integration

## Prerequisites Installed ✅
- Docker Desktop
- Docker Compose

## Quick Start (2 minutes)

### 1. Copy Environment Template
```bash
cp .env.example .env
```

### 2. Start Services
```bash
docker-compose up -d
```

### 3. Verify
```bash
curl http://localhost:8000/health
```

### 4. Run Tests
```bash
./test-apis.sh
```

### 5. Start Frontend (new terminal)
```bash
npm run dev
```

---

## Services Running After docker-compose up -d

| Service | URL | Purpose |
|---------|-----|---------|
| FastAPI Backend | http://localhost:8000 | API endpoints |
| MongoDB | localhost:27017 | Database |
| React Frontend | http://localhost:3000 | Web UI |

---

## Access Points

- **API Documentation**: http://localhost:8000/docs (Swagger UI)
- **Health Check**: http://localhost:8000/health
- **Admin Dashboard**: http://localhost:8000/admin/models-status
- **Frontend**: http://localhost:3000

---

## Useful Commands

```bash
# View all service logs
docker-compose logs -f

# View backend logs only
docker-compose logs -f backend

# Stop all services
docker-compose down

# Restart services
docker-compose restart

# Rebuild images
docker-compose build --no-cache
```

---

## If Something Goes Wrong

1. **Check logs**: `docker-compose logs`
2. **Restart**: `docker-compose restart`
3. **Rebuild**: `docker-compose down && docker-compose build && docker-compose up -d`
4. **Remove data**: `docker-compose down -v` (caution: deletes data)

---

## Connection Flow

```
Frontend (3000)
    ↓ HTTP
Backend (8000)
    ↓ Driver
MongoDB (27017)
```

All APIs, models, and honeypot run inside Docker!
