// Production: Use Docker backend
// Development: Use local backend or Docker
const BACKEND_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const BASE = BACKEND_URL

async function req(path, method = 'GET', body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  const token = localStorage.getItem('ep_token')
  if (token) opts.headers['Authorization'] = `Bearer ${token}`
  if (body) opts.body = JSON.stringify(body)

  const res  = await fetch(BASE + path, opts)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'API error')
  return data
}

// Phase 1+2: Submit biometric scores → get Argon2id params + session token
export async function submitScore({ theta, hExp, latentVector, userAgent, serverLoad }) {
  return req('/score', 'POST', {
    theta,
    h_exp:         hExp,
    server_load:   serverLoad ?? 0.5,
    user_agent:    userAgent ?? navigator.userAgent,
    latent_vector: latentVector ?? [],
  })
}

// Hash a password with RL-selected Argon2id params
export async function hashPassword({ plainPassword, theta, hExp }) {
  return req('/password/hash', 'POST', {
    plain_password: plainPassword,
    stored_hash:    '',
    theta,
    h_exp:          hExp,
  })
}

// Verify a password against stored hash
export async function verifyPassword({ plainPassword, storedHash }) {
  return req('/password/verify', 'POST', {
    plain_password: plainPassword,
    stored_hash:    storedHash,
    theta: 0.5,
    h_exp: 0.5,
  })
}

// Phase 4: Session verification heartbeat
export async function sendWatchdogHeartbeat({ userId, latentVector, eRec, trustScore }) {
  return req('/session/verify', 'POST', {
    session_token:  localStorage.getItem('ep_token') ?? '',
    user_id:        userId,
    latent_vector:  latentVector,
    e_rec:          eRec,
    trust_score:    trustScore,
  })
}

// Threat intel: get honeypot signatures
export async function getHoneypotSignatures() {
  return req('/honeypot/signatures')
}

// Health check
export async function healthCheck() {
  return req('/health')
}
