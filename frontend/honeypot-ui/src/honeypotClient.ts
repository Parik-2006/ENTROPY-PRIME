/**
 * src/honeypotClient.ts — HTTP client layer for the Honeypot UI.
 *
 * Responsibilities:
 *  1. POST /score              — run 4-stage pipeline, receive challenge config
 *  2. POST /honeypot/trigger   — report a decoy interaction (fire-and-forget)
 *  3. POST /honeypot/reward    — close MAB reward loop after shadow session
 *  4. GET  /honeypot/signatures — fetch harvested bot signatures (admin view)
 *
 * This client NEVER calls /auth/* or /session/verify — those belong to the
 * main app's API client (src/services/api.js). This file is scoped purely to
 * the Stage 2 honeypot/shadow pipeline.
 */

import type { ScoreResponse, TriggerRequest } from './types'

// ── Config ───────────────────────────────────────────────────────────────────

const BACKEND = import.meta.env.VITE_API_URL ?? ''  // empty = same origin (proxy)

// ── Core fetch wrapper ────────────────────────────────────────────────────────

async function post<T>(path: string, body: unknown, sessionToken?: string): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (sessionToken) headers['X-Session-Token'] = sessionToken

  const res = await fetch(`${BACKEND}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    keepalive: true,  // survives page-unload (important for trigger reports)
  })

  if (!res.ok) {
    const detail = await res.text().catch(() => `HTTP ${res.status}`)
    throw new Error(`[honeypotClient] ${path} → ${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`)
  if (!res.ok) throw new Error(`[honeypotClient] GET ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Run the full 4-stage pipeline. Returns the raw /score response.
 *
 * theta and h_exp default to values that look plausibly human so the shadow
 * UI can obtain a challenge config without a real biometric engine attached.
 * The actual main app (LoginPage.jsx) uses real values from biometrics.js.
 */
export async function runScore(params: {
  theta?: number
  h_exp?: number
  server_load?: number
  user_agent?: string
  latent_vector?: number[]
  fingerprint?: string
  // Phase 3 MVP — optional attacker-intent signals (drive attack classification)
  distinct_usernames?: number
  failed_attempts?: number
  password_attempts?: number
  request_rate?: number
  admin_path_hits?: number
  unique_paths?: number
  not_found_ratio?: number
}): Promise<ScoreResponse> {
  const payload = {
    theta:         params.theta         ?? 0.5,
    h_exp:         params.h_exp         ?? 0.5,
    server_load:   params.server_load   ?? 0.4,
    user_agent:    params.user_agent    ?? navigator.userAgent,
    latent_vector: params.latent_vector ?? [],
    fingerprint:   params.fingerprint   ?? '',
    distinct_usernames: params.distinct_usernames ?? 0,
    failed_attempts:    params.failed_attempts    ?? 0,
    password_attempts:  params.password_attempts  ?? 0,
    request_rate:       params.request_rate       ?? 0,
    admin_path_hits:    params.admin_path_hits     ?? 0,
    unique_paths:       params.unique_paths        ?? 0,
    not_found_ratio:    params.not_found_ratio     ?? 0,
  }
  return post<ScoreResponse>('/score', payload)
}

/**
 * Report a decoy interaction to the backend.
 *
 * Always fire-and-forget — never let network errors surface to calling code.
 * The backend validates the challenge signature server-side; invalid/expired
 * challenges are silently ignored (return HTTP 200 with {ok:true}).
 */
export async function reportTrigger(req: TriggerRequest): Promise<void> {
  try {
    await post('/honeypot/trigger', req)
  } catch (err) {
    // Intentionally swallow — bots must not learn that the trigger failed
    console.debug('[honeypotClient] trigger report failed (non-critical):', err)
  }
}

/**
 * Close the MAB reward loop after a shadow session ends.
 *
 * @param arm    - MAB arm index from the /score response (mab_arm field)
 * @param reward - float [-1, 1]; >0 = deception held, <0 = bot escaped
 */
export async function reportMabReward(arm: number, reward: number): Promise<void> {
  try {
    await post('/honeypot/reward', { arm, reward })
  } catch (err) {
    console.debug('[honeypotClient] MAB reward report failed:', err)
  }
}

/**
 * Fetch harvested bot signatures (admin dashboard).
 */
export async function fetchSignatures(): Promise<{
  signatures: Array<{
    timestamp: string
    user_agent: string
    theta: number
    ip_address: string
    path: string
  }>
  count: number
}> {
  return get('/honeypot/signatures')
}

// ── Phase 3 MVP — Shadow World + Threat Intel (additive) ──────────────────────
//
// After a shadow-routed "login success", the SDK navigates the attacker into a
// synthetic world served from /api/shadow/*.  Every call carries the session
// token as a bearer credential; the backend resolves which world (banking /
// shadow_admin) the session belongs to.  These helpers let FakeVault /
// FakeTerminal / ShadowDashboard render REAL backend-generated synthetic data
// instead of hardcoded props.

async function getAuthed<T>(path: string, sessionToken: string): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    headers: { Authorization: `Bearer ${sessionToken}` },
  })
  if (!res.ok) throw new Error(`[honeypotClient] GET ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

/** Discover which synthetic world this shadow session is in + its assets. */
export async function fetchShadowEnv(sessionToken: string): Promise<{
  world: string
  assets: string[]
  user: { role: string }
}> {
  return getAuthed('/api/shadow/me', sessionToken)
}

/** Generic shadow-world asset fetcher (banking: dashboard/accounts/transactions/…). */
export async function fetchShadowAsset<T = unknown>(
  asset: string,
  sessionToken: string,
  query: Record<string, string | number> = {},
): Promise<T> {
  const qs = Object.entries(query)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&')
  const suffix = qs ? `?${qs}` : ''
  return getAuthed<T>(`/api/shadow/${asset}${suffix}`, sessionToken)
}

/** Shadow Admin asset fetcher (users/logs/analytics/config/secrets). */
export async function fetchShadowAdmin<T = unknown>(
  asset: string,
  sessionToken: string,
  query: Record<string, string | number> = {},
): Promise<T> {
  return fetchShadowAsset<T>(`admin/${asset}`, sessionToken, query)
}

/** Defender dashboard: recorded attacker sessions (ThreatPage / ThreatIntel). */
export async function fetchDeceptionSessions(): Promise<{ sessions: any[] }> {
  return get('/admin/deception/sessions')
}

/** Defender dashboard: recorded attacker events. */
export async function fetchDeceptionEvents(sessionToken?: string): Promise<{ events: any[] }> {
  const suffix = sessionToken ? `?session_token=${encodeURIComponent(sessionToken)}` : ''
  return get(`/admin/deception/events${suffix}`)
}
