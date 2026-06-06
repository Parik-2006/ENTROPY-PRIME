# Integration Guide — Honeypot UI → Existing ENTROPY-PRIME App

This guide walks through integrating the Stage 2 honeypot frontend into your existing login/authentication flow **without breaking existing functionality**.

---

## Step 1: Install Dependencies

In `frontend/honeypot-ui/`:

```bash
cd frontend/honeypot-ui
npm install
```

This installs React 18, TypeScript, and Vite.

---

## Step 2: Verify Backend Contracts

Before integrating, ensure your backend matches these responses.

### Check backend/main.py

Verify `/score` endpoint returns:

```python
{
  "session_token": "ep_shadow_...",
  "shadow_mode": True/False,
  "argon2_params": {...},
  "action_label": "economy|standard|hard|punisher",
  "humanity_score": 0.XX,
  "entropy_score": 0.XX,
  "pipeline_confidence": "high|medium|low",
  "degraded": False,
  # When shadow_mode=True:
  "mab_arm": 0,  # or 1, 2 (arm selection)
  "challenge": {...},  # ChallengeConfig
}
```

### Check backend/models/stage2_honeypot.py

Verify `ChallengeConfig` and `DecoySpec` are defined and match [frontend/honeypot-ui/src/types.ts](src/types.ts).

### Check backend/main.py endpoints

Ensure these exist:
- `POST /score` — returns ScoreResponse
- `POST /honeypot/trigger` — accepts TriggerRequest, returns `{ok: true}`
- `POST /honeypot/reward` — accepts `{arm: int, reward: float}`, returns `{ok: true}`

---

## Step 3: Import the Hook in Your Auth Component

Find your main auth component (usually `src/pages/LoginPage.jsx` or `src/context/AuthContext.jsx`) and add:

```jsx
// At the top of your file:
import { useHoneypot } from '../../../frontend/honeypot-ui/src/useHoneypot'
```

Adjust the path based on your directory structure. The import path should resolve to `frontend/honeypot-ui/src/useHoneypot.ts`.

---

## Step 4: Initialize the Hook

In your login/auth component's logic (e.g., inside your login handler or component body):

```jsx
export function LoginPage() {
  const [authData, setAuthData] = useState(null)
  const [shadowMode, setShadowMode] = useState(false)
  
  // Initialize the honeypot hook
  const { applyScoreResponse, shadowMode: inShadowMode } = useHoneypot({
    sessionToken: authData?.session_token || '',
    onDecoyTriggered: (decoyId, kind, event) => {
      console.log('🤖 Honeypot triggered!', { decoyId, kind, event })
      // Optionally: POST to admin dashboard, alert, etc.
    },
  })
  
  // Store shadow mode state for rendering
  useEffect(() => {
    setShadowMode(inShadowMode)
  }, [inShadowMode])
  
  // ... rest of component
}
```

---

## Step 5: Feed /score Response into the Hook

After your existing login flow completes and you call `/score`, feed the response to the hook:

```jsx
async function handleLogin(email, password) {
  try {
    // 1. Authenticate (existing flow)
    const loginRes = await loginUser({ email, password })
    setAuthData(loginRes)
    
    // 2. Call /score (existing flow)
    const biometricTheta = await calculateBiometricTheta()  // from your biometric module
    const scoreRes = await submitScore({
      theta: biometricTheta,
      h_exp: entropyScore,
      server_load: serverLoad,
    })
    
    // 3. Apply to honeypot layer (NEW)
    applyScoreResponse(scoreRes)
    
    // 4. Check if shadow mode
    if (scoreRes.shadow_mode && scoreRes.challenge) {
      // Bot detected — route to shadow UI
      setShadowMode(true)
      return
    }
    
    // 5. Otherwise: render normal dashboard (existing flow)
    setLoggedIn(true)
  } catch (err) {
    setError(err.message)
  }
}
```

---

## Step 6: Conditional Rendering

In your render logic, check `shadowMode`:

```jsx
if (shadowMode) {
  // Render full shadow UI
  return (
    <ShadowDashboard 
      scoreResponse={lastScoreResponse} 
      devMode={process.env.NODE_ENV === 'development'}
    />
  )
}

// Otherwise: render your normal dashboard (unchanged)
return <Dashboard />
```

**Import ShadowDashboard** at the top:

```jsx
import { ShadowDashboard } from '../../../frontend/honeypot-ui/src/ShadowDashboard'
```

---

## Step 7: Test Locally

1. Start backend on port 8000:
   ```bash
   cd backend
   python -m uvicorn main:app --reload --port 8000
   ```

2. Start main app (e.g., Vite dev server):
   ```bash
   npm run dev  # in root or src/
   ```

3. Trigger shadow mode by providing **low `theta`** in `/score` request:
   ```javascript
   const scoreRes = await submitScore({
     theta: 0.05,  // Very bot-like
     h_exp: 0.5,
     server_load: 0.4,
   })
   ```

4. Expected behavior:
   - `scoreRes.shadow_mode === true`
   - `scoreRes.challenge` is present
   - FakeTerminal + FakeVault rendered instead of normal dashboard
   - Open DevTools → Network to see `/honeypot/trigger` requests

---

## Step 8: Production Build

Bundle honeypot UI into your main app build:

```bash
# Build honeypot-ui
cd frontend/honeypot-ui
npm run build

# Output: frontend/honeypot-ui/dist/
# TypeScript compiled to JavaScript
# React components bundled
# Ready to ship
```

Copy `dist/` assets to your production static folder, or include them in your main build process.

---

## Common Integration Patterns

### Pattern A: SPA with React Router

If using React Router, you can place shadow routing in a route guard:

```jsx
<Route 
  path="/dashboard" 
  element={
    shadowMode ? 
      <ShadowDashboard scoreResponse={scoreRes} /> 
      : <Dashboard />
  }
/>
```

### Pattern B: Conditional Component Wrapper

Wrap your dashboard in a component that checks shadow mode:

```jsx
function ProtectedDashboard() {
  const { shadowMode, lastScoreResponse } = useHoneypot({...})
  
  if (shadowMode) {
    return <ShadowDashboard scoreResponse={lastScoreResponse} />
  }
  return <Dashboard />
}
```

### Pattern C: Context API

Store `shadowMode` in your auth context:

```jsx
const AuthContext = createContext({
  shadowMode: false,
  applyScoreResponse: () => {},
})

export function AuthProvider({ children }) {
  const honeypot = useHoneypot({...})
  
  return (
    <AuthContext.Provider value={{ shadowMode: honeypot.shadowMode }}>
      {children}
    </AuthContext.Provider>
  )
}
```

---

## Debugging

### Enable dev mode

In honeypot-ui App.tsx, the dev panel is controlled by a query param:

```javascript
const DEV_MODE = new URLSearchParams(window.location.search).get('dev') === '1'
```

Access it at: `http://localhost:3000/dashboard?dev=1`

The dev panel shows:
- Current pipeline stage results
- Active decoys
- Trigger events in real-time
- MAB arm selection
- Watchdog output

### Check network requests

Open browser DevTools → Network tab and filter for:
- `/score` — /4-stage pipeline request/response
- `/honeypot/trigger` — decoy interaction reports
- `/honeypot/reward` — MAB reward closure

### Backend logs

Check your backend for:
```
[stage2_honeypot] Challenge created: challenge_id=...
[honeypot_trigger] Trigger received from session_token=...
[honeypot_reward] Reward: arm=X reward=Y
```

---

## Validation Checklist

- [ ] `frontend/honeypot-ui/` directory exists with all source files
- [ ] `src/types.ts` types match backend responses
- [ ] `useHoneypot.ts` imported in auth component
- [ ] Hook initialized with valid `sessionToken`
- [ ] `applyScoreResponse(scoreRes)` called after `/score`
- [ ] Shadow mode check: `if (scoreRes.shadow_mode && scoreRes.challenge)`
- [ ] `ShadowDashboard` rendered when in shadow mode
- [ ] Backend `/honeypot/trigger` and `/honeypot/reward` endpoints reachable
- [ ] Decoys present in `/score` response when shadow mode active
- [ ] Browser DevTools shows invisible decoy DOM elements injected
- [ ] Test with low `theta` to trigger shadow mode

---

## Troubleshooting

### "useHoneypot is not exported"

**Problem**: TypeScript can't find the import path.

**Solution**: Verify the path resolves correctly:
```bash
ls -la frontend/honeypot-ui/src/useHoneypot.ts
```

If using TypeScript in your main app, ensure `tsconfig.json` includes the path:
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@honeypot/*": ["frontend/honeypot-ui/src/*"]
    }
  }
}
```

Then import as:
```jsx
import { useHoneypot } from '@honeypot/useHoneypot'
```

### "Decoys not appearing in DOM"

**Problem**: No invisible decoy elements in page source.

**Solution**:
1. Verify `shadow_mode === true` and `challenge` is present in `/score` response
2. Check that `applyScoreResponse()` is called
3. Open DevTools and search for `__ep_hp_container__` in the DOM
4. If not found, check browser console for errors

### "Network error on /honeypot/trigger"

**Problem**: Decoy clicks don't post to backend.

**Solution**:
1. Verify backend `/honeypot/trigger` endpoint exists and is accessible
2. Check CORS headers (if frontend runs on different origin)
3. Verify request body matches `TriggerRequest` interface
4. Check backend `main.py` for `/honeypot/trigger` route handler

---

## Next: Production Deployment

Once integration is tested locally:

1. **Build honeypot-ui**: `npm run build` in `frontend/honeypot-ui/`
2. **Bundle with main app**: Copy `dist/` or include in your build pipeline
3. **Test in staging**: Run full pipeline with shadow mode
4. **Monitor**: Track honeypot trigger logs to refine MAB arm strategies
5. **Deploy**: Ship to production

Good luck! 🎭🤖
