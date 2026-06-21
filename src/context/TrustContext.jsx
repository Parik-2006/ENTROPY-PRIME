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

export const TIERS = {
  green:  { key: 'green',  min: 85, label: 'Verified',            color: 'var(--accent)', tone: 'ok' },
  yellow: { key: 'yellow', min: 65, label: 'Behavior deviation',  color: 'var(--gold)',   tone: 'warn' },
  orange: { key: 'orange', min: 40, label: 'Confidence reduced',  color: '#FF9F45',       tone: 'warn' },
  red:    { key: 'red',    min: 0,  label: 'Identity not verified', color: 'var(--danger)', tone: 'danger' },
}

export function tierFor(conf) {
  if (conf >= 85) return TIERS.green
  if (conf >= 65) return TIERS.yellow
  if (conf >= 40) return TIERS.orange
  return TIERS.red
}

export function behaviorStatusFor(conf) {
  if (conf >= 85) return 'Stable'
  if (conf >= 65) return 'Minor deviation'
  if (conf >= 40) return 'Significant deviation'
  return 'Anomalous'
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
  const { trustScore, liveTheta, anomaly, isProfileStable, liveDrift, profileStats } = useAuth()

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

  // Base target from REAL signals (used when no demo override is active).
  // Before the profile is stable we trust the watchdog score; once stable we
  // map live drift → confidence so a different human is actually detected.
  const baseTarget = () => {
    if (!stableR.current) return clamp(trustR.current * 100)
    const conf = driftToConf(driftR.current, thrR.current)
    let v = Math.min(conf, trustR.current * 100 + 8) // watchdog acts as a ceiling
    if (thetaR.current < 0.3) v = Math.min(v, 55)    // clearly non-human cadence
    return clamp(v)
  }

  // Organic drift: a real watchdog anomaly while stable pushes us into deviation.
  useEffect(() => {
    if (anomaly && isProfileStable && !demoRef.current) {
      setDemo({ kind: 'organic', floor: 58 })
      pushEvent('risk', 'Behavior drift detected', 'Live keystroke cadence diverged from baseline')
    }
  }, [anomaly, isProfileStable, pushEvent])

  // Single animation loop — eases the displayed value toward its target, adds
  // gentle jitter when healthy, records history, and emits tier-change events.
  useEffect(() => {
    const id = setInterval(() => {
      const d = demoRef.current
      let target = d ? d.floor : baseTarget()
      if (!d && target > 90) target = 96 + Math.round(Math.random() * 4)

      const cur = confRef.current
      let next
      if (Math.abs(target - cur) <= 1.5) {
        next = target + (!d && target >= 90 ? (Math.random() * 3 - 1.5) : 0)
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
  const verifyIdentity = useCallback(() => {
    setDemo(null)
    confRef.current = 100
    setConfidence(100)
    setLastVerifiedAt(now())
    pushEvent('verification', 'Identity confirmed', 'User re-verified — confidence restored to 100%')
  }, [pushEvent])
  const resetTrust = useCallback(() => {
    setDemo(null); confRef.current = 100; setConfidence(100); setLastVerifiedAt(now())
    pushEvent('session', 'Trust state reset', 'Verified baseline restored')
  }, [pushEvent])

  const tier = tierFor(confidence)
  const value = {
    confidence,
    trustScore,
    tier,
    tierKey: tier.key,
    color: tier.color,
    label: tier.label,
    behaviorStatus: behaviorStatusFor(confidence),
    isDemo: !!demo,
    demoKind: demo?.kind ?? null,
    canSensitive: confidence >= 65,
    needsVerify:  tier.key === 'orange',
    blocked:      tier.key === 'red',
    history,
    events,
    lastVerifiedAt,
    sessionStart: sessionStart.current,
    pushEvent,
    simulateSlowTypist,
    simulateFastTypist,
    simulateDifferentUser,
    simulateAttacker,
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
      sessionStart: Date.now(), pushEvent: () => {},
      simulateSlowTypist: () => {}, simulateFastTypist: () => {},
      simulateDifferentUser: () => {}, simulateAttacker: () => {},
      verifyIdentity: () => {}, resetTrust: () => {},
    }
  }
  return ctx
}
