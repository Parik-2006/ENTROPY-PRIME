# Runtime Dependency Audit — PyTorch

> Audit only. No code changed. Production entrypoint = `uvicorn backend.main:app`
> (per `render.yaml`).

## TL;DR
torch is a **hard, load-time dependency** of the backend. It is imported at the top of
`backend/main.py` and the torch-backed models are instantiated at **module import time**,
so `backend.main` cannot even be imported without torch — the app **cannot start**
without it as currently written.

---

## 1. Every file importing torch

| File | Import | In production import graph? |
|---|---|---|
| `backend/main.py:73` | `import torch` (top-level, unconditional) | **YES** — the app module |
| `backend/models/cnn1d.py:22-24` | `import torch`, `torch.nn`, `torch.nn.functional` | **YES** — imported by `main.py:110` |
| `backend/models/ppo.py:16-18` | `import torch`, `nn`, `F` | **YES** — `main.py:108` (Stage-4 watchdog) |
| `backend/models/ppo_agents.py:15-18` | `import torch`, `nn`, `F`, `Categorical` | **YES** — `main.py:109` (Stage-3 governor) |
| `backend/models/dqn.py:20-21,88` | `import torch`, `nn`; `torch.optim` (in method) | **YES** — `main.py:106` (governor preset) |
| `backend/models/test_pipeline.py:398,404` | `import torch` (inside test fns) | No — test only |
| `backend/train.py:16-18` | `import torch`, `nn`, `optim` | No — offline training script |
| `backend/models/train_cnn1d.py:18-20` | `import torch`, `nn`, `optim` | No — offline training script |
| `backend/test_stage1_simple.py` | references torch | No — test/dev script |

(`framework/` re-exports the same `backend.models.*` via the facade, but the production
process runs `backend.main:app`, so the four model modules above are the live importers.)

## 2. Do those code paths execute in production?

Yes — at two points:

- **Import time** (unavoidable): `backend/main.py:73` imports torch; `main.py:106-110`
  import `DQNAgent / PPOAgent / PPOPolicyAgent / CNN1D`, each of which does a top-level
  `import torch`.
- **Module load** (immediately after import): the agents/model are **instantiated at
  module scope** — `main.py:168-181`:
  ```py
  dqn_agent     = DQNAgent(state_dim=3,  action_dim=4)
  ppo_agent     = PPOAgent(state_dim=10, action_dim=3)        # Stage 4 watchdog
  gov_ppo_agent = PPOPolicyAgent(state_dim=5, action_dim=4)   # Stage 3 governor
  cnn_model     = CNN1D(input_channels=1, out_dim=32)
  ```
  These build `torch.nn` modules/tensors. The lifespan then calls `_load_checkpoints()`
  (`main.py:191+`) which `torch.load`s `*.pt` checkpoints into the agents.
- **Per-request**: the pipeline runs these models (governor/watchdog/CNN) on the
  model-backed endpoints (see §4).

No torch import is guarded (no `try/except ImportError`, no `HAS_TORCH` flag) in any of
the four production modules — verified in `cnn1d.py`, `ppo.py`, `ppo_agents.py`, `dqn.py`.

## 3. Can the application start without torch?

**No.** With torch uninstalled, `uvicorn backend.main:app` fails during import with
`ModuleNotFoundError: No module named 'torch'` at `backend/main.py:73` (and again at the
model imports / instantiation `:168-181`). Uvicorn never reaches app creation, so **no**
endpoint — not even `/health` or `/auth/*` — is served.

Making torch optional is feasible but requires **code changes** (out of scope for this
audit): lazy/guarded imports, deferring model instantiation, and a numpy fallback or
graceful-degrade path for the governor/watchdog/CNN inference. The browser already
computes humanity θ via TensorFlow.js, but the **server** governor (Argon2 preset),
watchdog drift action, and CNN latent paths currently rely on torch.

## 4. Which endpoints depend on torch?

Because torch loads at import (§3), **every** endpoint is gated at startup. Beyond that,
the endpoints that **functionally** invoke torch-backed models:

| Endpoint | Torch-backed model used |
|---|---|
| `POST /score` | full pipeline: CNN/governor (DQN+PPOPolicy)/watchdog (PPO) |
| `POST /telemetry` | pipeline |
| `POST /session/verify` | `run_watchdog` → Stage-4 `PPOAgent` |
| `POST /session/trust` | trust combine (watchdog/governor) |
| `POST /password/hash`, `POST /password/verify` | governor `DQNAgent` (Argon2 preset) |
| `POST /biometric/extract`, `POST /stage1/analyze`, `POST /analyze` | Stage-1 / CNN |
| `GET /admin/pipeline-debug`, `GET /admin/models-status` | pipeline / model state |

Endpoints with **no functional** torch use (but still unavailable if torch is missing,
because the app won't boot): `/health`, `/auth/*`, `/me`, `/honeypot/*`,
`/biometric/profile` (+ `/status`, `/reset`), `/admin/onboarding-summary`,
`/admin/honeypot/dashboard`, webhooks, notifications. These store/read MongoDB and run no
model inference.

## 5. Estimated memory savings if torch were removed

Caveat: depends entirely on which wheel `torch==2.11.0` resolves to.

| Resource | If default (CUDA) wheel | If CPU-only wheel |
|---|---|---|
| **Install / image size** | ~**2–5 GB** freed (torch + `nvidia-*` cu12 deps: cublas/cudnn/etc.) | ~**0.7–1 GB** freed (~180–200 MB download) |
| **Runtime RSS** (process memory) | ~**150–400 MB** freed (`import torch` loads libtorch + MKL/OpenMP; the tiny models add little) | ~**150–350 MB** freed |
| **Cold-start time** | seconds faster (no large lib load + `torch.load`) | seconds faster |

Context: a Render free/starter instance has ~512 MB RAM — `import torch` alone can be a
large fraction of that, which is the most likely cause of the build/boot risk flagged in
`docs/RENDER_SETUP.md` / `docs/DEPLOYMENT_READY.md`. The actual ML models here are very
small (Conv1d 1→32, MLP PPO/DQN); essentially **all** the cost is torch itself, not the
weights.

## Verdict
- torch is **required** to run the backend today (load-time, unconditional).
- It is **not** required by the banking/auth/persistence endpoints functionally — only by
  the Stage-1/3/4 model inference paths — so it *could* be made optional with code
  changes, but as written, removing torch breaks startup entirely.
- Removing/optionalizing torch would save roughly **0.7–5 GB of image size** and
  **~150–400 MB of runtime RAM**, and is the highest-leverage fix for low-memory hosting.
