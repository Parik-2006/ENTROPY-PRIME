/**
 * src/services/deception.js — Deception Demo Lab API client.
 *
 * Talks to the REAL backend deception endpoints (no mock data):
 *   POST /score                     → runs the actual classifier + honeypot routing
 *   GET  /api/shadow/*              → synthetic banking world (Bearer = shadow token)
 *   GET  /api/shadow/admin/*        → synthetic shadow-admin world
 *   GET  /admin/deception/sessions  → recorded attacker sessions (threat intel)
 *   GET  /admin/deception/events    → recorded attacker events
 *
 * This module is used ONLY by the Deception Demo Lab. It does not touch the
 * production auth/session flow.
 */

// Same base-URL resolution as services/api.js (kept independent on purpose).
const BACKEND_URL =
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_BACKEND_URL ||
  import.meta.env.VITE_API_URL ||
  (typeof window !== 'undefined' ? '' : 'http://localhost:8000')

const url = (path) =>
  BACKEND_URL.endsWith('/') ? BACKEND_URL.slice(0, -1) + path : BACKEND_URL + path

async function getJSON(path, bearer) {
  const headers = {}
  if (bearer) headers['Authorization'] = `Bearer ${bearer}`
  const res = await fetch(url(path), { headers })
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json()
}

async function postJSON(path, body) {
  const res = await fetch(url(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `POST ${path} → ${res.status}`)
  return data
}

// ── Attack catalogue ──────────────────────────────────────────────────────────
// Each entry maps to REAL classifier signals (framework.deception.classifier).
// `presentation` controls only how the attacker view is rendered; the backend
// classification, routing, and threat-intel logging are always authoritative.
// Final presentation set — exactly three credible, finished attack demos.
export const ATTACKS = {
  credential_stuffing: {
    label:    'Credential Stuffing',
    icon:     '🔑',
    expect:   'Banking Shadow Environment',
    threat:   'high',
    signals:  { distinct_usernames: 18, failed_attempts: 22 },
    userAgent:'python-requests/2.31',
    presentation: 'banking',
  },
  recon: {
    label:    'Reconnaissance',
    icon:     '🛰',
    expect:   'Recon Sandbox Terminal',
    threat:   'high',
    signals:  { admin_path_hits: 4, unique_paths: 32, not_found_ratio: 0.6 },
    userAgent:'curl/8.1',
    presentation: 'terminal',
  },
  brute_force: {
    label:    'Brute Force',
    icon:     '🔨',
    expect:   'Argon2id + Tarpit',
    threat:   'medium',
    signals:  { password_attempts: 14, failed_attempts: 14 },
    userAgent:'Hydra/9.5',
    presentation: 'bruteforce',
  },
}

const rand = () => Math.random().toString(36).slice(2, 14)

/**
 * Launch one attack simulation against the REAL pipeline.
 * Sends a bot-like θ so Stage 1+2 shadow-route, plus the classifier signals.
 * Returns the raw /score response (session_token, shadow_mode, attack_class,
 * redirect, mab_arm, humanity_score, pipeline_confidence, …).
 */
export async function simulateAttack(attackKey) {
  const a = ATTACKS[attackKey]
  if (!a) throw new Error(`unknown attack: ${attackKey}`)
  return postJSON('/score', {
    theta:       0.04,                  // definite bot → shadow route
    h_exp:       0.2,
    server_load: 0.4,
    user_agent:  a.userAgent,
    fingerprint: `demo_${attackKey}_${rand()}`,
    latent_vector: [],
    ...a.signals,
  })
}

// ── Shadow world (attacker view) ──────────────────────────────────────────────
// Optional: the attacker environments render entirely client-side for demo
// stability, but these are kept for backends that serve live synthetic data.
export const getShadowEnv = (token) => getJSON('/api/shadow/me', token)

// NOTE: the Threat-Intelligence client functions (getDeceptionSummary/Sessions/
// Events) were removed for the presentation build — that module is retired.
