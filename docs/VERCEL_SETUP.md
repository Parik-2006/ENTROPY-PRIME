# Vercel Setup (Frontend SPA)

The frontend is a Vite + React SPA. `vercel.json` is committed with the correct
framework, build, output, and SPA-fallback config.

## Project settings
| Setting | Value |
|---|---|
| Framework Preset | **Vite** |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Install Command | `npm install` |
| Root Directory | repository root (`/`) |

`vercel.json` also adds the SPA rewrite so client-side routes (e.g. `/app/dashboard`,
`/enroll`, legacy routes) resolve to `index.html` instead of 404:
```json
{ "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }
```

## Environment variables (Vercel → Project → Settings → Environment Variables)

Set for **Production** (and Preview if desired):

```
VITE_API_BASE_URL = https://entropy-prime.onrender.com
VITE_BACKEND_URL  = https://entropy-prime.onrender.com
```

- These are read at **build time** by `src/services/api.js`. After changing them,
  trigger a redeploy so the new value is baked into the bundle.
- `VITE_API_URL` is still honored as a legacy fallback but is not required.

## Verify after deploy
1. Open the Vercel URL → app loads, theme toggle works, no console errors.
2. Network tab: API calls go to `https://entropy-prime.onrender.com/...` (not the
   Vercel domain).
3. Deep-link a route (e.g. `/app/security`) and refresh → loads via SPA fallback.
4. Login/enroll round-trips succeed (confirms CORS + backend reachable).
