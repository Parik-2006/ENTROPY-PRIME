/**
 * src/types.ts — Shared type contracts for the Entropy Prime Honeypot UI.
 *
 * These mirror the Python dataclasses in:
 *   backend/models/stage2_honeypot.py  (DecoySpec, ChallengeConfig)
 *   backend/pipeline/contracts.py      (PipelineOutput, WatchdogResult)
 *   backend/main.py                    (/score response shape)
 *
 * ⚠ Do NOT invent fields here. Every field must be present in the backend
 *   response documented in DEMO_README.md or in the source Python code.
 */

// ── Decoy element kinds ──────────────────────────────────────────────────────
// Matches DecoySpec.kind in stage2_honeypot.py
export type DecoyKind = 'input' | 'button' | 'link' | 'checkbox'

// ── DecoySpec ────────────────────────────────────────────────────────────────
// Mirrors: backend/models/stage2_honeypot.py :: DecoySpec
export interface DecoySpec {
  decoy_id: string
  kind: DecoyKind
  name: string
  label: string
  autocomplete: string
  tab_index: number
}

// ── ChallengeConfig ──────────────────────────────────────────────────────────
// Mirrors: backend/models/stage2_honeypot.py :: ChallengeConfig.to_dict()
export interface ChallengeConfig {
  challenge_id: string
  arm: number          // 0=Tarpit, 1=Echo, 2=Canary
  expires_at: number   // Unix epoch (seconds)
  signature: string    // HMAC-SHA256 over challenge_id|arm|expires_at|decoy_ids
  decoys: DecoySpec[]
}

// ── WatchdogResult (nested in /score response) ───────────────────────────────
// Mirrors: backend/pipeline/contracts.py :: WatchdogResult
export interface WatchdogResult {
  action: 'ok' | 'passive_reauth' | 'disable_sensitive_api' | 'force_logout'
  trust_score: number  // [0, 1]
  e_rec: number        // autoencoder reconstruction error
  confidence: 'high' | 'medium' | 'low'
  reason: string
}

// ── /score response ───────────────────────────────────────────────────────────
// Mirrors: backend/main.py :: @app.post("/score") return value
export interface ScoreResponse {
  session_token: string
  shadow_mode: boolean
  argon2_params: { m: number; t: number; p: number }
  action_label: string    // 'economy'|'standard'|'hard'|'punisher'
  humanity_score: number  // [0, 1]
  entropy_score: number   // [0, 1]
  pipeline_confidence: 'high' | 'medium' | 'low'
  degraded: boolean
  // Present only when shadow_mode=true AND arm >= 0
  mab_arm?: number
  // Present only when shadow_mode=true
  challenge?: ChallengeConfig
  // Present only when latent_vector was provided (Stage 4)
  watchdog?: WatchdogResult
}

// ── /honeypot/trigger request ─────────────────────────────────────────────────
// Mirrors: backend/main.py :: HoneypotTriggerReq
export interface TriggerRequest {
  challenge_id: string
  arm: number
  expires_at: number
  signature: string
  decoy_ids: string[]
  triggered_decoy: string
  trigger_event: string   // 'focus'|'input'|'change'|'click'
  trigger_kind: string    // DecoyKind
  session_token: string
}

// ── MAB arm label (informational) ────────────────────────────────────────────
export const ARM_LABELS: Record<number, string> = {
  0: 'Tarpit (Heavy Form Decoys)',
  1: 'Echo (Mirrored Field Names)',
  2: 'Canary (Silent Audit)',
}

// ── Threat gate response from /score when globally flagged ──────────────────
export interface ThreatGatedResponse extends ScoreResponse {
  threat_gate: 'GLOBALLY_FLAGGED'
}
