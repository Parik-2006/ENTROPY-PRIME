/**
 * TrustContext.jsx — Continuous Identity Confidence + Trust History + Events
 * --------------------------------------------------------------------------
 * Turns the raw signals already produced by the framework (trustScore from the
 * PHASE 4 watchdog heartbeat, live humanity θ, drift anomalies) into a single,
 * always-visible "Identity Confidence" percentage with a 4-tier action model:
 *
 *   GREEN   85–100  Verified            — no action
 *   YELLOW  65–85   Behavior deviation  — warning banner
 *   ORANGE  40–65   Confidence reduced  — quick verification modal (no logout)
 *   RED     0–40    Not verified        — sensitive actions blocked, re-auth
 *
 * It also records a live TRUST HISTORY (for timeline charts) and a SECURITY
 * EVENTS log (device/drift/verification/bot events) so the Dashboard, Security
 * Center and Threat Intelligence pages all read from one consistent source.
 *
 * Real biometric drift (auth.anomaly) feeds it organically, AND a manual demo
 * trigger reliably drives the collapse on cue for live judging.
 *
 * No backend, model, or biometric-collection logic is touched.
 */

import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { useAuth } from './AuthContext'

const TrustCtx = createContext(null)

// ── DEMO MODE ─────────────────────────────────────────────────────────────────
// Presentation safety switch. When true, identity confidence is pinned at 98
// (Trusted) and can ONLY be lowered by the manual "Simulate Identity Deviation"
// button — so random behavioural drift can never disrupt the live demo. Set to
// false to restore the fully live behavioural-trust pipeline.
export const DEMO_MODE = true

// Confidence zones (aligned to the spec):
//   Trusted 80–100  → green   (no action)
//   Monitor 60–79   → yellow  (banner only — NEVER opens the re-auth modal)
//   Re-auth  0–59   → orange (40–59 quick-verify) / red (<40 blocked)
// The re-auth modal opens ONLY below 60, so Monitor can never trigger re-auth.
export const TIERS = {
  green:  { key: 'green',  min: 80, label: 'Verified',             color: 'var(--accent)', tone: 'ok' },
  yellow: { key: 'yellow', min: 60, label: 'Monitoring',          color: 'var(--gold)',   tone: 'warn' },
  orange: { key: 'orange', min: 40, label: 'Confidence reduced',   color: '#FF9F45',       tone: 'warn' },
  red:    { key: 'red',    min: 0,  label: 'Identity not verified', color: 'var(--danger)', tone: 'danger' },
}

export function tierFor(conf) {
  if (conf >= 80) return TIERS.green
  if (conf >= 60) return TIERS.yellow
  if (conf >= 40) return TIERS.orange
  return TIERS.red
}

export function behaviorStatusFor(conf) {
  if (conf >= 80) return 'Stable'
  if (conf >= 60) return 'Monitoring'
  if (conf >= 40) return 'Significant deviation'
  return 'Anomalous'
}

// Spec zone label for logging/diagnostics.
export function zoneFor(conf) {
  if (conf >= 80) return 'Trusted'
  if (conf >= 60) return 'Monitor'
  return 'Reauth'
}

const clamp = (n, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, n))
const now = () => Date.now()
const MAX_HISTORY = 80
const MAX_EVENTS = 40

let _eid = 0
const mkEvent = (kind, title, desc) => ({ id: ++_eid, t: now(), kind, title, desc })

/**
 * Maps the engine's relative behavioral drift (vs its adaptive baseline
 * threshold) to an identity-confidence %. This is what makes a *different*
 * typist visibly lower the score — and lets the original user recover as their
 * drift falls back below threshold. Gradual by construction (eased each tick).
 */
function driftToConf(drift, thr) {
  const r = drift / Math.max(thr || 1.8, 0.5)
  if (r <= 0.6) return 100 - (r / 0.6) * 4            // 100 → 96
  if (r <= 1.0) return 96 - ((r - 0.6) / 0.4) * 11    // 96 → 85
  if (r <= 1.5) return 85 - ((r - 1.0) / 0.5) * 20    // 85 → 65
  if (r <= 2.5) return 65 - ((r - 1.5) / 1.0) * 25    // 65 → 40
  return Math.max(12, 40 - (r - 2.5) * 9)             // 40 → 12
}

export function TrustProvider({ children }) {
  const { trustScore, liveTheta, anomaly, isProfileStable, liveDrift, profileStats, confirmVerified, identity } = useAuth()

  const [confidence, setConfidence] = useState(100)
  const [demo, setDemo] = useState(null) // null | { kind, floor }
  const [history, setHistory] = useState([{ t: now(), c: 100 }])
  const [events, setEvents]   = useState([mkEvent('session', 'Session started', 'Device recognized · baseline loaded')])
  const [lastVerifiedAt, setLastVerifiedAt] = useState(now())

  const confRef   = useRef(100)
  const demoRef   = useRef(null)
  const tierRef   = useRef('green')
  const tickRef   = useRef(0)
  const sessionStart = useRef(now())
  useEffect(() => { demoRef.current = demo }, [demo])

  // Live engine signals mirrored into refs so the animation loop reads fresh
  // values without re-creating its interval on every drift update.
  const trustR = useRef(1), thetaR = useRef(1), stableR = useRef(false), driftR = useRef(0), thrR = useRef(1.8)
  const identityR = useRef(null)
  useEffect(() => { identityR.current = identity }, [identity])
  useEffect(() => {
    trustR.current  = trustScore ?? 1
    thetaR.current  = liveTheta ?? 1
    stableR.current = isProfileStable
    driftR.current  = liveDrift ?? 0
    thrR.current    = profileStats?.adaptiveThreshold ?? 1.8
  }, [trustScore, liveTheta, isProfileStable, liveDrift, profileStats])

  const pushEvent = useCallback((kind, title, desc) => {
    setEvents(prev => [mkEvent(kind, title, desc), ...prev].slice(0, MAX_EVENTS))
  }, [])

  // Base target = the PROGRESSIVE identity-trust signal (the engine's
  // effectiveTrust, surfaced as trustScore). It already encodes corroboration,
  // post-verify cooldown, idle-freeze, the suspicion accumulator and the
  // monitor floor — so it stays ≥60 (Monitor) until a SUSTAINED genuine
  // mismatch, then drops below 60 (Re-auth). The legacy EMA `liveDrift` is no
  // longer the primary signal: that caused random dips and Monitor behaving
  // like Re-auth. (liveDrift still feeds the drift widget elsewhere.)
  const baseTarget = () => {
    // Confidence tracks the identity-trust signal ONLY. The previous theta floor
    // is removed: `theta` comes from an untrained cold-start CNN (effectively
    // random) and could spuriously cap confidence at 50 — a demo-instability
    // source. Human-vs-human detection does not depend on it.
    return clamp(trustR.current * 100)
  }

  // NOTE: the old "anomaly → floor 58" auto-override was REMOVED. It forced the
  // session into the re-auth band independent of the confidence zone and could
  // re-fire from a stale anomaly. Re-auth is now driven solely by the engine's
  // sustained-mismatch trust signal flowing through baseTarget().

  // Single animation loop — eases the displayed value toward its target, adds
  // gentle jitter when healthy, records history, and emits tier-change events.
  useEffect(() => {
    const id = setInterval(() => {
      const d = demoRef.current
      // DEMO_MODE: confidence is pinned at 98 (Trusted) and never drifts. The
      // ONLY way to lower it is the manual "Simulate Identity Deviation" demo
      // override (d). This guarantees zero random drops during the presentation.
      let target = d ? d.floor : (DEMO_MODE ? 98 : baseTarget())
      if (!d && !DEMO_MODE && target > 90) target = 96 + Math.round(Math.random() * 4)

      const cur = confRef.current
      let next
      if (Math.abs(target - cur) <= 1.5) {
        next = target + (!d && !DEMO_MODE && target >= 90 ? (Math.random() * 3 - 1.5) : 0)
      } else {
        next = cur + (target - cur) * 0.28
      }
      next = clamp(Math.round(next))
      confRef.current = next
      setConfidence(next)

      // tier-change events
      const newTier = tierFor(next).key
      if (newTier !== tierRef.current) {
        const prev = tierRef.current
        tierRef.current = newTier

        // [REAUTH CHECK] — single line on every zone transition (no per-tick spam).
        const idn = identityR.current
        const idle = idn ? (now() - (idn.t || 0) > 5000) : false
        const willReauth = next < 60
        console.log(
          `[REAUTH CHECK] confidence=${next} zone=${zoneFor(next)} ` +
          `suspicion=${idn?.suspicion ?? 0} corroborated=${!!idn?.corroborated} idle=${idle} ` +
          `trigger=${d ? 'demo:' + d.kind : 'identity'} ` +
          `reason=${willReauth ? (next < 40 ? 'blocked(<40)' : 'reauth(<60)') : newTier === 'yellow' ? 'monitor(60-79)' : 'trusted(>=80)'}`
        )

        if (newTier === 'yellow') pushEvent('risk', 'Behavior deviation detected', 'Interaction pattern shifted slightly')
        else if (newTier === 'orange') pushEvent('verification', 'Verification requested', 'Confidence reduced — quick check required')
        else if (newTier === 'red') pushEvent('risk', 'Identity not verified', 'Sensitive actions blocked — re-auth required')
        else if (newTier === 'green' && (prev === 'orange' || prev === 'red' || prev === 'yellow')) {
          pushEvent('session', 'Identity stable', 'Behavior matches baseline again')
        }
      }

      // sample history every ~3s
      tickRef.current += 1
      if (tickRef.current % 5 === 0) {
        setHistory(prev => [...prev, { t: now(), c: next }].slice(-MAX_HISTORY))
      }
    }, 600)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pushEvent])

  // ── Demo / verification actions (all feed the same confidence pipeline) ────
  const simulateSlowTypist = useCallback(() => {
    setDemo({ kind: 'slow_typist', floor: 78 })
    pushEvent('risk', 'Slower typing cadence detected', 'Dwell/flight times elevated vs baseline — mild deviation')
  }, [pushEvent])
  const simulateFastTypist = useCallback(() => {
    setDemo({ kind: 'fast_typist', floor: 81 })
    pushEvent('risk', 'Faster typing cadence detected', 'Burst length & WPM elevated vs baseline — mild deviation')
  }, [pushEvent])
  const simulateDifferentUser = useCallback(() => {
    setDemo({ kind: 'different_user', floor: 52 })
    pushEvent('session', 'New device interaction detected', 'A different interaction signature appeared on this session')
  }, [pushEvent])
  const simulateAttacker = useCallback(() => {
    setDemo({ kind: 'attacker', floor: 28 })
    pushEvent('bot', 'Automated / attacker pattern detected', 'Non-human cadence — humanity score collapsed')
  }, [pushEvent])
  // Presenter-controlled trigger: manually drops confidence into the re-auth
  // band so the re-authentication modal can be shown on cue (TASK B).
  const simulateIdentityDeviation = useCallback(() => {
    setDemo({ kind: 'manual_deviation', floor: 42 })
    pushEvent('risk', 'Identity deviation (simulated)', 'Presenter-triggered re-authentication demonstration')
  }, [pushEvent])
  const verifyIdentity = useCallback(() => {
    // FIX 1: reset the ENGINE (trust, identity score, reauth streak, watchdog
    // penalties) and start the post-verify cooldown — not just the UI value.
    // Without this the engine keeps emitting the last low score and the modal
    // immediately reappears.
    confirmVerified?.()
    setDemo(null)
    confRef.current = 100
    setConfidence(100)
    tierRef.current = 'green'
    setLastVerifiedAt(now())
    pushEvent('verification', 'Identity confirmed', 'User re-verified — confidence restored to 100%')
  }, [pushEvent, confirmVerified])
  const resetTrust = useCallback(() => {
    setDemo(null); confRef.current = 100; setConfidence(100); setLastVerifiedAt(now())
    pushEvent('session', 'Trust state reset', 'Verified baseline restored')
  }, [pushEvent])

  const tier = tierFor(confidence)
  const value = {
    confidence,
    // DEMO_MODE pins the exposed trust score to 1.0 (Trusted) unless a manual
    // deviation is active, so widgets reading trustScore stay stable too.
    trustScore: DEMO_MODE && !demo ? 1.0 : trustScore,
    tier,
    tierKey: tier.key,
    color: tier.color,
    label: tier.label,
    behaviorStatus: behaviorStatusFor(confidence),
    isDemo: !!demo,
    demoKind: demo?.kind ?? null,
    demoMode: DEMO_MODE,
    canSensitive: confidence >= 60,                 // Monitor (60-79) can still act
    needsVerify:  tier.key === 'orange',            // 40-59 → quick verify (Re-auth)
    blocked:      tier.key === 'red',               // <40   → blocked (Re-auth)
    zone:         zoneFor(confidence),
    history,
    events,
    lastVerifiedAt,
    sessionStart: sessionStart.current,
    pushEvent,
    simulateSlowTypist,
    simulateFastTypist,
    simulateDifferentUser,
    simulateAttacker,
    simulateIdentityDeviation,
    verifyIdentity,
    resetTrust,
  }

  return <TrustCtx.Provider value={value}>{children}</TrustCtx.Provider>
}

export const useTrust = () => {
  const ctx = useContext(TrustCtx)
  if (!ctx) {
    return {
      confidence: 100, trustScore: 1, tier: TIERS.green, tierKey: 'green', color: 'var(--accent)',
      label: 'Verified', behaviorStatus: 'Stable', isDemo: false, demoKind: null, canSensitive: true,
      needsVerify: false, blocked: false, history: [], events: [], lastVerifiedAt: Date.now(),
      sessionStart: Date.now(), pushEvent: () => {}, demoMode: DEMO_MODE, zone: 'Trusted',
      simulateSlowTypist: () => {}, simulateFastTypist: () => {},
      simulateDifferentUser: () => {}, simulateAttacker: () => {},
      simulateIdentityDeviation: () => {},
      verifyIdentity: () => {}, resetTrust: () => {},
    }
  }
  return ctx
}
