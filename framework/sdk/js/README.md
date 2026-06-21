# Entropy Prime — JavaScript SDK

Browser SDK for the Entropy Prime behavioral security framework. Captures
behavioral signals client-side and scores them through the framework API. Raw
keystrokes/mouse never leave the browser.

## Two tiers

| Tier | Humanity score source | When |
|---|---|---|
| Lightweight (built-in) | timing-variance proxy | demos, simple sites, no build step |
| Production | full TensorFlow.js CNN engine (`src/services/biometrics.js`) via `ep.setEngine(...)` | real deployments |

## Quick start (`<script type="module">`)
```html
<form id="login-form">
  <input name="email" />
  <input name="password" type="password" />
  <input type="hidden" id="ep_token" name="ep_token" />
  <button>Sign in</button>
</form>

<script type="module">
  import { EntropyPrime } from './entropy-prime.js'

  const ep = new EntropyPrime({
    apiUrl: 'http://localhost:8000',         // talks to /v1 by default
    onScore:   (score, label) => console.log(`humanity ${score.toFixed(2)} → ${label}`),
    onSession: (token) => (document.querySelector('#ep_token').value = token),
  })
  ep.attach(document.querySelector('#login-form'))

  document.querySelector('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault()
    const result = await ep.flush()       // POST /v1/score
    if (result.shadow_mode) {
      alert('Bot behavior detected — request shadow-routed.')
    } else {
      e.target.submit()
    }
  })
</script>
```

## Production engine
```js
import { EntropyPrimeClient } from '/src/services/biometrics.js'
const engine = new EntropyPrimeClient(); await engine.init()
ep.setEngine(engine)   // now flush() uses the CNN theta + real 32-dim latent
```

## API
| Method | Purpose |
|---|---|
| `attach(target?)` / `detach()` | start/stop behavioral capture |
| `flush()` | compute signals → `POST /v1/score` → `{ session_token, shadow_mode, action_label, ... }` |
| `register(email, pw)` / `login(email, pw)` | enroll / authenticate |
| `verify(userId, latent, eRec)` | continuous-auth heartbeat |
| `trust(userId, risk)` | transaction gate (allow/challenge/deny) |
| `setEngine(engine)` | swap in the tfjs production engine |
