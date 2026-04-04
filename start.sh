#!/bin/bash
# Entropy Prime — unified start script

set -e

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  ███████╗███╗   ██╗████████╗██████╗  ██████╗ ██████╗ ██╗   ██╗"
echo "  ██╔════╝████╗  ██║╚══██╔══╝██╔══██╗██╔═══██╗██╔══██╗╚██╗ ██╔╝"
echo "  █████╗  ██╔██╗ ██║   ██║   ██████╔╝██║   ██║██████╔╝ ╚████╔╝ "
echo "  ██╔══╝  ██║╚██╗██║   ██║   ██╔══██╗██║   ██║██╔═══╝   ╚██╔╝  "
echo "  ███████╗██║ ╚████║   ██║   ██║  ██║╚██████╔╝██║        ██║   "
echo "  ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝        ╚═╝  "
echo "  ██████╗ ██████╗ ██╗███╗   ███╗███████╗"
echo "  ██╔══██╗██╔══██╗██║████╗ ████║██╔════╝"
echo "  ██████╔╝██████╔╝██║██╔████╔██║█████╗  "
echo "  ██╔═══╝ ██╔══██╗██║██║╚██╔╝██║██╔══╝  "
echo "  ██║     ██║  ██║██║██║ ╚═╝ ██║███████╗"
echo "  ╚═╝     ╚═╝  ╚═╝╚═╝╚═╝     ╚═╝╚══════╝"
echo -e "${NC}"
echo -e "  ${CYAN}Zero-Trust Behavioral Biometrics Engine${NC}"
echo "  ─────────────────────────────────────────────"
echo ""

BACKEND_DIR="$(cd "$(dirname "$0")/backend" && pwd)"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Check Python ───────────────────────────────────────────────────────────────
echo -e "${YELLOW}[1/4] Checking Python environment...${NC}"
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}✗ python3 not found. Install Python 3.10+${NC}"; exit 1
fi
PY=$(python3 --version 2>&1)
echo -e "${GREEN}✓ ${PY}${NC}"

# ── Check / create venv ────────────────────────────────────────────────────────
if [ ! -d "$ROOT_DIR/.venv" ]; then
  echo -e "${YELLOW}[2/4] Creating virtual environment...${NC}"
  python3 -m venv "$ROOT_DIR/.venv"
fi
source "$ROOT_DIR/.venv/bin/activate"
echo -e "${YELLOW}[2/4] Installing backend dependencies...${NC}"
pip install -q -r "$BACKEND_DIR/requirements.txt"
echo -e "${GREEN}✓ Backend dependencies ready${NC}"

# ── Check Node ─────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[3/4] Checking Node.js...${NC}"
if ! command -v node &>/dev/null; then
  echo -e "${RED}✗ node not found. Install Node.js 18+${NC}"; exit 1
fi
NODE=$(node --version 2>&1)
echo -e "${GREEN}✓ Node ${NODE}${NC}"

# ── Install frontend deps ──────────────────────────────────────────────────────
if [ ! -d "$ROOT_DIR/node_modules" ]; then
  echo -e "${YELLOW}[3/4] Installing frontend dependencies (first run)...${NC}"
  cd "$ROOT_DIR" && npm install
fi
echo -e "${GREEN}✓ Frontend dependencies ready${NC}"

# ── Generate secrets if not set ────────────────────────────────────────────────
export EP_SESSION_SECRET="${EP_SESSION_SECRET:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"
export EP_SHADOW_SECRET="${EP_SHADOW_SECRET:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"

# ── Optional RL checkpoint ─────────────────────────────────────────────────────
if [ -f "$ROOT_DIR/checkpoints/governor.pt" ]; then
  export EP_RL_CHECKPOINT="$ROOT_DIR/checkpoints/governor.pt"
  echo -e "${GREEN}✓ RL checkpoint found: checkpoints/governor.pt${NC}"
else
  echo -e "${YELLOW}  ℹ  No RL checkpoint found — governor starts with random policy${NC}"
  echo -e "     Run: ${CYAN}python backend/train.py --episodes 100000${NC} to pre-train"
fi

echo ""
echo -e "${CYAN}[4/4] Starting services...${NC}"
echo ""

# ── Start backend ──────────────────────────────────────────────────────────────
echo -e "${GREEN}► Backend  → http://localhost:8000${NC}"
echo -e "${GREEN}► Docs     → http://localhost:8000/docs${NC}"
cd "$BACKEND_DIR"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend to be ready
echo -n "  Waiting for backend"
for i in $(seq 1 20); do
  sleep 0.5
  if curl -s http://localhost:8000/health >/dev/null 2>&1; then
    echo -e " ${GREEN}✓${NC}"
    break
  fi
  echo -n "."
done

# ── Start frontend ─────────────────────────────────────────────────────────────
echo -e "${GREEN}► Frontend → http://localhost:3000${NC}"
cd "$ROOT_DIR"
npm run dev &
FRONTEND_PID=$!

echo ""
echo -e "${CYAN}─────────────────────────────────────────────${NC}"
echo -e "${GREEN}  Entropy Prime is running!${NC}"
echo -e "  Open: ${CYAN}http://localhost:3000${NC}"
echo -e "${CYAN}─────────────────────────────────────────────${NC}"
echo ""
echo "  Press Ctrl+C to stop all services"
echo ""

# ── Cleanup on exit ────────────────────────────────────────────────────────────
cleanup() {
  echo ""
  echo -e "${YELLOW}Shutting down...${NC}"
  kill $BACKEND_PID  2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  deactivate 2>/dev/null || true
  echo -e "${GREEN}Done.${NC}"
}
trap cleanup INT TERM

wait $FRONTEND_PID
