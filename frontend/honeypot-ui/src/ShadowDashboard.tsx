/**
 * src/ShadowDashboard.tsx — top-level coordinator for a routed session.
 *
 * Rendered when shadow_mode=true in the /score response. It:
 *   1. Boots the DecoyManager (invisible DOM instrumentation) in the background
 *   2. Renders the believable, API-driven environment (ShadowEnvironment)
 *   3. Closes the MAB reward loop after an engagement window
 *   4. Mounts the operator-only DefenderPanel — ONLY when devMode is set
 *
 * The subject (attacker) sees nothing but an ordinary banking / admin app. If
 * the live data service is unreachable, a brand-neutral maintenance screen is
 * shown instead of a blank page — it reveals nothing about the infrastructure.
 */

import React, { useEffect, useRef, useState } from 'react'
import type { ScoreResponse } from './types'
import { DecoyManager } from './DecoyRenderer'
import { reportMabReward } from './honeypotClient'
import { ShadowEnvironment } from './ShadowEnvironment'
import { DefenderPanel } from './DefenderPanel'

interface ShadowDashboardProps {
  scoreResponse: ScoreResponse
  /** Show the operator-only panel (default: false — subjects never see it) */
  devMode?: boolean
}

interface TriggerEvent {
  decoyId: string
  kind: string
  event: string
  ts: number
}

const MAB_REWARD_DELAY_MS = 8_000  // wait 8s before closing reward loop

export function ShadowDashboard({ scoreResponse, devMode = false }: ShadowDashboardProps) {
  const [triggerEvents, setTriggerEvents] = useState<TriggerEvent[]>([])
  const mabRewardSent = useRef(false)
  const managerRef = useRef<DecoyManager | null>(null)

  // Boot the DecoyManager once on mount — invisible DOM instrumentation keeps
  // running beneath the believable environment (unchanged backend integration).
  useEffect(() => {
    const manager = new DecoyManager()
    managerRef.current = manager

    if (scoreResponse.challenge) {
      manager.applyChallenge(scoreResponse.challenge, {
        sessionToken: scoreResponse.session_token,
        onTriggered: (decoyId, kind, event) => {
          setTriggerEvents((prev) => [
            { decoyId, kind, event, ts: Date.now() },
            ...prev.slice(0, 19),
          ])
        },
        onDestroyed: () => {},
      })
    }

    return () => manager.destroyAll()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Close the MAB reward loop after the subject has spent time in the
  // environment. Fires once on mount so the reward loop is preserved
  // regardless of the believable UI the subject sees.
  useEffect(() => {
    if (mabRewardSent.current) return
    mabRewardSent.current = true
    const arm = scoreResponse.mab_arm ?? 0
    const t = setTimeout(() => {
      const reward = triggerEvents.length > 0 ? 1.0 : 0.5
      reportMabReward(arm, reward)
      console.debug(`[ShadowDashboard] reward sent: arm=${arm} reward=${reward}`)
    }, MAB_REWARD_DELAY_MS)
    return () => clearTimeout(t)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // The subject sees ONLY the believable, API-driven environment. If the live
  // data service is unreachable, fall back to the maintenance screen.
  return (
    <>
      <ShadowEnvironment
        scoreResponse={scoreResponse}
        fallback={<MaintenanceScreen />}
      />
      {devMode && <DefenderPanel scoreResponse={scoreResponse} />}
    </>
  )
}

// ── Maintenance fallback (shown only if the live data service is unreachable) ──
// Believable, brand-neutral banking maintenance screen. It reveals nothing
// about the underlying infrastructure and preserves the subject's belief that
// they are inside a real banking application experiencing a transient outage.
function MaintenanceScreen() {
  const ref = React.useMemo(
    () => Math.random().toString(36).slice(2, 10).toUpperCase(),
    [],
  )
  return (
    <div style={ms.page}>
      <header style={ms.topbar}>
        <div style={ms.brand}><span style={ms.brandMark}>◆</span> Online Banking</div>
        <span style={ms.secure}>● Secure session</span>
      </header>
      <div style={ms.body}>
        <div style={ms.card}>
          <div style={ms.icon}>↻</div>
          <h1 style={ms.title}>Account information temporarily unavailable</h1>
          <p style={ms.text}>
            Your account services are currently undergoing scheduled
            synchronization. Please refresh in a few moments.
          </p>
          <button style={ms.btn} onClick={() => window.location.reload()}>Refresh</button>
          <div style={ms.ref}>Reference: {ref}</div>
        </div>
      </div>
    </div>
  )
}

const ms: Record<string, React.CSSProperties> = {
  page:   { minHeight: '100vh', background: '#f4f6f9', color: '#1f2a37', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  topbar: { height: 60, background: '#0b3d91', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px' },
  brand:  { fontSize: 18, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 },
  brandMark: { color: '#9fc0ff' },
  secure: { fontSize: 12, color: '#bfe3c9' },
  body:   { display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 60px)', padding: 24 },
  card:   { width: '100%', maxWidth: 460, background: '#fff', border: '1px solid #e3e8ee', borderRadius: 14, padding: '40px 36px', textAlign: 'center', boxShadow: '0 6px 24px rgba(15,42,55,0.06)' },
  icon:   { width: 56, height: 56, margin: '0 auto 20px', borderRadius: '50%', background: '#eaf1fd', color: '#0b5bd3', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, animation: 'spin 1.4s linear infinite' },
  title:  { fontSize: 19, fontWeight: 700, margin: '0 0 12px', color: '#1f2a37' },
  text:   { fontSize: 14, lineHeight: 1.6, color: '#5b6b7d', margin: '0 0 24px' },
  btn:    { padding: '10px 28px', background: '#0b5bd3', color: '#fff', border: 'none', borderRadius: 7, cursor: 'pointer', fontSize: 14, fontWeight: 600 },
  ref:    { marginTop: 20, fontSize: 11, color: '#9aa7b4', letterSpacing: 0.5 },
}
