# Docker Setup Guide for Entropy Prime

## Quick Start with Docker Compose

### Prerequisites
- Docker (https://www.docker.com/products/docker-desktop)
- Docker Compose (usually included with Docker Desktop)

### Step 1: Build and Run All Services
From the project root (`/workspaces/ENTROPY-PRIME`), run:

```bash
docker-compose up -d
```

This will:
- Build the backend image
- Start MongoDB (listening on localhost:27017)
- Start the FastAPI backend (listening on localhost:8000)

### Step 2: Verify Services Are Running
```bash
docker-compose ps
```

You should see:
- entropy-prime-mongodb (healthy)
- entropy-prime-backend (running)

### Step 3: Test the Backend
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok"}
```

### Step 4: Access Honeypot Data
```bash
curl http://localhost:8000/honeypot/signatures
```

---

## Common Docker Commands

### View Logs
```bash
docker-compose logs -f backend
docker-compose logs -f mongodb
```

### Stop Services
```bash
docker-compose down
```

### Stop and Remove Data
```bash
docker-compose down -v
```

### Rebuild Images
```bash
docker-compose build --no-cache
```

### Run Backend Only (Local MongoDB)
```bash
docker build -t entropy-prime-backend ./backend
docker run -p 8000:8000 -e MONGODB_URL=mongodb://host.docker.internal:27017 entropy-prime-backend
```

---

## Environment Variables
Edit `docker-compose.yml` under `backend.environment` to customize:
- `MONGODB_URL` — MongoDB connection string
- `EP_SESSION_SECRET` — Session secret key
- `EP_SHADOW_SECRET` — Shadow/honeypot secret key

---

## Troubleshooting

### MongoDB Connection Refused
- Wait 10-15 seconds for MongoDB to initialize
- Check logs: `docker-compose logs mongodb`

### Backend Port Already in Use
- Change port in `docker-compose.yml`: `"9000:8000"` instead of `"8000:8000"`

### Permission Denied (Linux)
```bash
sudo usermod -aG docker $USER
newgrp docker
```

---

## Production Deployment
For production:
1. Use environment variables or secrets management instead of hardcoded values
2. Set `MONGODB_URL` to your MongoDB Atlas connection string
3. Use strong, random values for `EP_SESSION_SECRET` and `EP_SHADOW_SECRET`
4. Add SSL/TLS certificates
5. Use a reverse proxy (Nginx, Traefik) for routing

---

Ready to go! Just run `docker-compose up -d` and you're set.
