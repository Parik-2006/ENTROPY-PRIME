# Frontend — Honeypot UI (Stage 2 Frontend)

A standalone React/TypeScript app that implements the **browser-side** of Stage 2 (Offensive Deception). It lives in `frontend/honeypot-ui/` and integrates **with** the existing main app in `src/`, without replacing it.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Main app  (src/pages/LoginPage.jsx)                │
│  ├── calls submitScore() via src/services/api.js    │
│  └── receives ScoreResponse                         │
│                                                     │
│  useHoneypot() hook  ← add this one import          │
│  ├── applyScoreResponse(res)                        │
│  │   ├── shadow_mode=false → no-op                  │
│  │   └── shadow_mode=true  → inject decoys          │
│  │         DecoyManager → DecoyRenderer              │
│  │         ├── DOM: invisible inputs/buttons/links   │
│  │         ├── monitor: focus/input/change/click     │
│  │         └── POST /honeypot/trigger on interaction │
│  └── MAB reward timer → POST /honeypot/reward        │
│                                                     │
│  ShadowDashboard  (optional full shadow UI)         │
│  ├── FakeTerminal  (animated pipeline output)       │
│  └── FakeVault     (arm-adaptive fake admin panel)  │
└─────────────────────────────────────────────────────┘
```

---

## Files

| File | Purpose |
|------|---------|
| `src/types.ts` | TypeScript contracts mirroring backend Python dataclasses |
| `src/honeypotClient.ts` | HTTP client: `/score`, `/honeypot/trigger`, `/honeypot/reward` |
| `src/DecoyRenderer.ts` | DOM decoy injection + event monitoring |
| `src/useHoneypot.ts` | React hook — bridge for the main app |
| `src/ShadowDashboard.tsx` | Full shadow-mode UI coordinator |
| `src/FakeTerminal.tsx` | Animated fake terminal output |
| `src/FakeVault.tsx` | Arm-adaptive fake admin panel (Tarpit/Echo/Canary) |
| `src/App.tsx` | Standalone diagnostic probe UI |
| `src/main.tsx` | React entry point |

---

## Integration with Main App

### Quick Start

Add **one import** to your main app's login/auth component (e.g., `src/pages/LoginPage.jsx` or `src/context/AuthContext.jsx`):

```jsx
import { useHoneypot } from '../../../frontend/honeypot-ui/src/useHoneypot'
```

Then, after your `submitScore()` call succeeds:

```jsx
const { applyScoreResponse, shadowMode } = useHoneypot({
  sessionToken: authData.session_token,
  onDecoyTriggered: (decoyId, kind, event) => {
    console.log('🤖 Bot detected!', { decoyId, kind, event })
    // Optionally log to honeypot dashboard / alert admin
  },
})

// After login succeeds and /score is called:
const scoreData = await submitScore({
  theta: biometricTheta,
  h_exp: entropyScore,
  server_load: currentLoad,
})

// Feed it into the honeypot layer:
applyScoreResponse(scoreData)

// In JSX: if shadow mode, show fake UI instead of real dashboard
if (shadowMode) {
  return <ShadowDashboard scoreResponse={scoreData} />
}
// Otherwise: render normal dashboard
```

---

## Backend Contract

The honeypot frontend **consumes exactly one response type** — the `/score` endpoint:

### /score Response (backend/main.py)

```typescript
interface ScoreResponse {
  session_token: string
  shadow_mode: boolean
  argon2_params: { m: number; t: number; p: number }
  action_label: string    // 'economy'|'standard'|'hard'|'punisher'
  humanity_score: number  // [0, 1]
  entropy_score: number   // [0, 1]
  pipeline_confidence: 'high' | 'medium' | 'low'
  degraded: boolean
  mab_arm?: number                // Present when shadow_mode=true
  challenge?: ChallengeConfig      // Present when shadow_mode=true
  watchdog?: WatchdogResult        // Present when Stage 4 provided latent vector
}
```

### /honeypot/trigger Request (Backend validates & logs)

When a decoy is clicked/filled:

```typescript
interface TriggerRequest {
  challenge_id: string
  arm: number
  expires_at: number
  signature: string       // HMAC-SHA256(challenge_id|arm|expires_at|decoy_ids)
  decoy_ids: string[]
  triggered_decoy: string
  trigger_event: string   // 'focus'|'input'|'change'|'click'
  trigger_kind: string    // DecoyKind
  session_token: string
}
```

Backend validates signature and logs the interaction. **Frontend never invents fields.**

---

## Running Standalone

Honeypot UI can also run as a **diagnostic probe** (e.g., for testing):

```bash
cd frontend/honeypot-ui
npm install
npm run dev
# Opens http://localhost:3001
```

The dev server proxies `/score`, `/honeypot/*`, etc. to `http://localhost:8000` (FastAPI backend).

Add `?dev=1` to enable slider controls and debug panel:
```
http://localhost:3001?dev=1
```

---

## Key Design Decisions

1. **Stateless decoy injection**: Each challenge is a discrete DOM tree. Multiple challenges can be active (different tabs, rapid re-scoring), but dedup by `challenge_id`.

2. **Fire-and-forget trigger reports**: If the network fails, bots never learn it failed. Errors are swallowed.

3. **MAB reward closure**: After 8 seconds of observation, the hook reports a reward (+1.0 if decoys were triggered, +0.3 if silent). This closes the MAB learning loop.

4. **Arm-adaptive fake UI**: Tarpit shows heavy forms, Echo shows mirrored JSON, Canary shows canary-token-embedded tables. Arm is chosen by MAB and returned in `/score` response.

5. **No auth coupling**: This module never calls `/auth/*` or `/session/verify`. It only consumes `/score` and posts to `/honeypot/*`.

---

## Browser Compatibility

- Modern Chromium (bots typically use)
- Firefox (bots sometimes use)
- Safari (rare for bots)

Decoy rendering uses standard DOM APIs; no polyfills needed.

---

## Troubleshooting

### Decoys not triggering?
- Check browser DevTools → Application → "Storage" to verify localStorage is enabled
- Verify `/honeypot/trigger` endpoint is reachable (check VITE_API_URL or proxy config)
- Check backend logs for `[stage2_honeypot]` messages

### Shadow mode never activating?
- Ensure `theta` sent to `/score` is < 0.3 (increases likelihood of shadow route)
- Check backend logs to see if `/score` is running all 4 stages
- Verify `mab_arm` is present in `/score` response

### Types don't match backend?
- Audit [backend/models/stage2_honeypot.py](backend/models/stage2_honeypot.py) and [backend/main.py](backend/main.py)
- The `DecoySpec`, `ChallengeConfig`, and `ScoreResponse` must exactly mirror Python dataclasses
- Do not add fields in frontend that don't exist in the backend response

---

## Next Steps

1. **Copy** this frontend to your production build
2. **Wire the hook** into your login flow
3. **Test** with low `theta` to trigger shadow mode
4. **Monitor** honeypot trigger logs in your backend admin panel
5. **Iterate** MAB arm strategies based on captured signatures

See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for detailed step-by-step instructions.
