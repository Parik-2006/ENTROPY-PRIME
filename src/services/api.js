/**
 * Entropy Prime — API Client v3
 * Consumes the 4-stage pipeline response contracts.
 *
 * Every function returns a typed-by-convention object.
 * Pipeline-specific fields (confidence, degraded, watchdog)
 * are surfaced so the UI can reflect model certainty.
 */

const BACKEND_URL = import.meta.env.VITE_API_URL || (typeof window !== 'undefined' ? '' : 'http://localhost:8000')

// ── Core fetch wrapper ────────────────────────────────────────────────────────

async function req(path, method = 'GET', body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  const token = localStorage.getItem('ep_token')
  if (token) opts.headers['X-Session-Token'] = token
  if (body)  opts.body = JSON.stringify(body)

  const url = BACKEND_URL.endsWith('/') ? BACKEND_URL.slice(0, -1) + path : BACKEND_URL + path
  const res  = await fetch(url, opts)
  const data = await res.json()

  if (!res.ok) {
    let errorMsg = data.detail || `API error ${res.status}`
    if (Array.isArray(data.detail)) {
      errorMsg = data.detail.map(err =>
        err.msg ? `${err.loc?.join('.')}: ${err.msg}` : JSON.stringify(err)
      ).join('; ')
    }
    console.error(`[API] ${res.status} ${path}:`, {
      status:       res.status,
      detail:       data.detail,
      errorMsg,
      fullResponse: data,
    })
    throw new Error(errorMsg)
  }
  return data
}

// ── Stage 1+2+3+4: Full pipeline score ───────────────────────────────────────

/**
 * Submit biometric signals through the full 4-stage pipeline.
 *
 * @returns {Promise<ScoreResult>}
 * ScoreResult {
 *   session_token:       string
 *   shadow_mode:         boolean        // true = bot shadow-routed
 *   argon2_params:       { m, t, p }
 *   action_label:        string         // 'economy'|'standard'|'hard'|'punisher'
 *   humanity_score:      number [0,1]
 *   entropy_score:       number [0,1]
 *   pipeline_confidence: 'high'|'medium'|'low'
 *   degraded:            boolean        // true = ≥1 stage used fallback
 *   watchdog?:           { action, trust_score, e_rec }
 *   mab_arm?:            number         // present only when shadow_mode=true
 * }
 */
export async function submitScore({ theta, hExp, latentVector, userAgent, serverLoad }) {
  const payload = {
    theta,
    h_exp:         hExp,
    server_load:   serverLoad ?? 0.5,
    user_agent:    userAgent  ?? navigator.userAgent,
    latent_vector: latentVector ?? [],
  }
  console.log('[submitScore] Payload:', {
    theta:                payload.theta,
    h_exp:                payload.h_exp,
    latent_vector_len:    payload.latent_vector.length,
    latent_vector_valid:  payload.latent_vector.length === 0 || payload.latent_vector.length === 32,
    server_load:          payload.server_load,
  })
  return req('/score', 'POST', payload)
}

/**
 * Persist the active user's biometric profile after typing in the profile-build page.
 */
export async function syncBiometricProfile({
  theta,
  hExp,
  latentVector,
  practiceText,
  keyboardStats,
  pointerStats,
  profileStats,
  liveDrift,
  serverLoad,
} = {}) {
  return req('/biometric/profile', 'POST', {
    theta,
    h_exp:          hExp,
    latent_vector:  latentVector  ?? [],
    practice_text:  practiceText  ?? '',
    keyboard_stats: keyboardStats ?? {},
    pointer_stats:  pointerStats  ?? {},
    profile_stats:  profileStats  ?? {},
    live_drift:     liveDrift,
    server_load:    serverLoad    ?? 0.5,
  })
}

// ── Password ──────────────────────────────────────────────────────────────────

/**
 * Hash a password. Governor (DQN) selects the Argon2id preset.
 *
 * @returns {Promise<HashResult>}
 * HashResult {
 *   hash:          string
 *   action:        string
 *   elapsed_ms:    number
 *   argon2_params: { m, t, p }
 *   confidence:    'high'|'medium'|'low'
 *   fallback:      boolean   // true = DQN was bypassed
 * }
 */
export async function hashPassword({ plainPassword, theta, hExp }) {
  return req('/password/hash', 'POST', {
    plain_password: plainPassword,
    stored_hash:    '',
    theta,
    h_exp:          hExp,
  })
}

export async function verifyPassword({ plainPassword, storedHash }) {
  return req('/password/verify', 'POST', {
    plain_password: plainPassword,
    stored_hash:    storedHash,
    theta:          0.5,
    h_exp:          0.5,
  })
}

// ── Stage 4: Watchdog heartbeat ───────────────────────────────────────────────

/**
 * Session watchdog heartbeat. Runs PPO → fallback rules.
 *
 * @returns {Promise<WatchdogResult>}
 * WatchdogResult {
 *   action:      'ok'|'passive_reauth'|'disable_sensitive_apis'|'force_logout'
 *   trust_score: number [0,1]
 *   e_rec:       number         // autoencoder reconstruction error
 *   confidence:  'high'|'medium'|'low'
 *   reason:      string         // diagnostic string
 * }
 *
 * @param {object} params
 * @param {string}   params.userId
 * @param {number[]} params.latentVector
 * @param {number}   params.eRec
 * @param {number}   params.trustScore
 * @param {number}   [params.behavioralDrift]     - live drift score from the biometric engine
 * @param {number}   [params.adaptiveThreshold]   - current dynamic anomaly threshold
 * @param {string[]} [params.selectedFeatures]    - feature names active in the current window
 * @param {number}   [params.sampleCount]         - total persisted samples in the profile
 */
export async function sendWatchdogHeartbeat({
  userId,
  latentVector,
  eRec,
  trustScore,
  behavioralDrift,
  adaptiveThreshold,
  selectedFeatures,
  sampleCount,
}) {
  return req('/session/verify', 'POST', {
    session_token:      localStorage.getItem('ep_token') ?? '',
    user_id:            userId,
    latent_vector:      latentVector,
    e_rec:              eRec,
    trust_score:        trustScore,
    behavioral_drift:   behavioralDrift,
    adaptive_threshold: adaptiveThreshold,
    selected_features:  selectedFeatures,
    sample_count:       sampleCount,
  })
}

// ── Stage 3 MAB feedback ──────────────────────────────────────────────────────

/**
 * Report a reward signal back to the MAB deception agent.
 * Call this when a shadow session ends.
 *
 * @param {number} arm     - MAB arm index returned in the /score response
 * @param {number} reward  - float in [-1, 1]; >0 = deception held
 */
export async function reportHoneypotReward(arm, reward) {
  return req('/honeypot/reward', 'POST', { arm, reward })
}

// ── Threat intel ──────────────────────────────────────────────────────────────

export async function getHoneypotSignatures() {
  return req('/honeypot/signatures')
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function registerUser({ email, plainPassword }) {
  return req('/auth/register', 'POST', { email, plain_password: plainPassword })
}

export async function loginUser({ email, plainPassword }) {
  return req('/auth/login', 'POST', { email, plain_password: plainPassword })
}

export async function logoutUser(sessionToken) {
  return req(`/auth/logout?session_token=${encodeURIComponent(sessionToken)}`, 'POST')
}

export async function fetchMe(sessionToken = localStorage.getItem('ep_token')) {
  const opts = {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  }
  if (sessionToken) opts.headers['X-Session-Token'] = sessionToken
  const url = BACKEND_URL.endsWith('/') ? BACKEND_URL.slice(0, -1) + '/me' : BACKEND_URL + '/me'
  const res = await fetch(url, opts)
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.detail || `API error ${res.status}`)
  }
  return data
}

export async function resetBiometricProfile(sessionToken = localStorage.getItem('ep_token'), reason = 'user_request') {
  const opts = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  }
  if (sessionToken) opts.headers['X-Session-Token'] = sessionToken
  const url = BACKEND_URL.endsWith('/') ? BACKEND_URL.slice(0, -1) + '/biometric/profile/reset' : BACKEND_URL + '/biometric/profile/reset'
  const res = await fetch(url, {
    ...opts,
    body: JSON.stringify({ reason }),
  })
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.detail || `API error ${res.status}`)
  }
  return data
}

// ── Debug / admin ─────────────────────────────────────────────────────────────

/**
 * Dry-run the pipeline with synthetic inputs.
 * Returns full per-stage breakdown including confidence and fallback flags.
 *
 * @returns {Promise<PipelineDebugResult>}
 */
export async function debugPipeline({ theta = 0.5, hExp = 0.5, serverLoad = 0.4 } = {}) {
  return req(`/admin/pipeline-debug?theta=${theta}&h_exp=${hExp}&server_load=${serverLoad}`)
}

export async function getModelsStatus() {
  return req('/admin/models-status')
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function healthCheck() {
  return req('/health')
}

// ── Watchdog action helpers ───────────────────────────────────────────────────

/**
 * Maps watchdog action strings to UI-level severity levels.
 * @param {'ok'|'passive_reauth'|'disable_sensitive_apis'|'force_logout'} action
 * @returns {'ok'|'warn'|'danger'|'critical'}
 */
export function watchdogSeverity(action) {
  return {
    ok:                     'ok',
    passive_reauth:         'warn',
    disable_sensitive_apis: 'danger',
    force_logout:           'critical',
  }[action] ?? 'ok'
}

/**
 * Maps pipeline_confidence to a numeric weight [0,1] for UI indicators.
 * @param {'high'|'medium'|'low'} confidence
 * @returns {number}
 */
export function confidenceWeight(confidence) {
  return { high: 1.0, medium: 0.6, low: 0.3 }[confidence] ?? 0.5
}