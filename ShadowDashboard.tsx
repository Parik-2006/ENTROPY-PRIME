/**
 * src/ShadowDashboard.tsx — Top-level shadow-mode UI coordinator.
 *
 * Rendered when shadow_mode=true in the /score response. Orchestrates:
 *   1. DecoyManager  — injects + monitors invisible DOM decoys
 *   2. FakeTerminal  — animated terminal output shown to the bot
 *   3. FakeVault     — arm-adaptive fake admin panel
 *   4. MAB reward    — fires /honeypot/reward after observation window
 *   5. Status panel  — real-time deception state (visible in dev mode only)
 *
 * Layout:
 *   - If DEV_MODE: split-pane (left = status, right = fake UI)
 *   - Otherwise:   full-screen fake UI (bots see only this)
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import type { ScoreResponse } from './types'
import { ARM_LABELS } from './types'
import { DecoyManager } from './DecoyRenderer'
import { FakeTerminal } from './FakeTerminal'
import { FakeVault } from './FakeVault'
import { reportMabReward } from './honeypotClient'

interface ShadowDashboardProps {
  scoreResponse: ScoreResponse
  /** Show the developer status panel (default: false — bots never see it) */
  devMode?: boolean
}

type Phase = 'terminal' | 'vault'

interface TriggerEvent {
  decoyId: string
  kind: string
  event: string
  ts: number
}

const MAB_REWARD_DELAY_MS = 8_000  // wait 8s before closing reward loop

export function ShadowDashboard({ scoreResponse, devMode = false }: ShadowDashboardProps) {
  const [phase,         setPhase]         = useState<Phase>('terminal')
  const [triggerEvents, setTriggerEvents] = useState<TriggerEvent[]>([])
  const [mabRewardSent, setMabRewardSent] = useState(false)
  const [activeDecoys,  setActiveDecoys]  = useState(0)
  const managerRef = useRef<DecoyManager | null>(null)

  // Boot the DecoyManager once on mount
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
        onDestroyed: () => {
          setActiveDecoys(manager.activeChallengeCount)
        },
      })
      setActiveDecoys(manager.activeChallengeCount)
    }

    return () => manager.destroyAll()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Transition terminal → vault after terminal finishes
  const handleTerminalDone = useCallback(() => {
    setPhase('vault')
  }, [])

  // Send MAB reward when terminal signals it's ready
  const handleMabRewardReady = useCallback(
    (arm: number) => {
      if (mabRewardSent) return
      setMabRewardSent(true)
      // Positive reward: deception held (bot stayed in sandbox)
      setTimeout(() => {
        const reward = triggerEvents.length > 0 ? 1.0 : 0.3
        reportMabReward(arm, reward)
        console.debug(`[ShadowDashboard] MAB reward sent: arm=${arm} reward=${reward}`)
      }, MAB_REWARD_DELAY_MS)
    },
    [mabRewardSent, triggerEvents.length],
  )

  const arm      = scoreResponse.mab_arm ?? 0
  const armLabel = ARM_LABELS[arm] ?? `Arm ${arm}`

  return (
    <div style={styles.root}>
      {devMode && (
        <aside style={styles.devPanel}>
          <DevStatusPanel
            scoreResponse={scoreResponse}
            arm={arm}
            armLabel={armLabel}
            triggerEvents={triggerEvents}
            mabRewardSent={mabRewardSent}
            activeDecoys={activeDecoys}
            phase={phase}
          />
        </aside>
      )}

      <main style={styles.main(devMode)}>
        {phase === 'terminal' ? (
          <div style={styles.terminalWrap}>
            <FakeTerminal
              scoreResponse={scoreResponse}
              onMabRewardReady={handleMabRewardReady}
            />
            <button
              style={styles.continueBtn}
              onClick={handleTerminalDone}
            >
              Continue to Dashboard →
            </button>
          </div>
        ) : (
          <FakeVault scoreResponse={scoreResponse} />
        )}
      </main>
    </div>
  )
}

// ── Developer status panel ────────────────────────────────────────────────────

interface DevStatusPanelProps {
  scoreResponse: ScoreResponse
  arm: number
  armLabel: string
  triggerEvents: TriggerEvent[]
  mabRewardSent: boolean
  activeDecoys: number
  phase: Phase
}

function DevStatusPanel({
  scoreResponse, arm, armLabel,
  triggerEvents, mabRewardSent, activeDecoys, phase,
}: DevStatusPanelProps) {
  return (
    <div style={styles.devInner}>
      <div style={styles.devTitle}>⚙ SHADOW DEBUG PANEL</div>
      <div style={styles.devNote}>Only visible in devMode=true</div>

      <Section title="Pipeline Output">
        <Row label="shadow_mode"        value={String(scoreResponse.shadow_mode)} accent="danger" />
        <Row label="session_token"      value={scoreResponse.session_token.slice(0, 24) + '…'} />
        <Row label="humanity_score"     value={scoreResponse.humanity_score.toFixed(4)} />
        <Row label="action_label"       value={scoreResponse.action_label} />
        <Row label="pipeline_conf"      value={scoreResponse.pipeline_confidence} />
        <Row label="degraded"           value={String(scoreResponse.degraded)} />
      </Section>

      <Section title="MAB / Honeypot">
        <Row label="arm"                value={`${arm} — ${armLabel}`} accent="warn" />
        <Row label="active challenges"  value={String(activeDecoys)} />
        <Row label="reward sent"        value={mabRewardSent ? 'YES' : 'pending'} accent={mabRewardSent ? 'green' : undefined} />
        <Row label="ui phase"           value={phase} />
      </Section>

      {scoreResponse.challenge && (
        <Section title="Challenge">
          <Row label="challenge_id" value={scoreResponse.challenge.challenge_id.slice(0, 16) + '…'} />
          <Row label="decoys"       value={String(scoreResponse.challenge.decoys.length)} />
          <Row label="expires_at"   value={new Date(scoreResponse.challenge.expires_at * 1000).toLocaleTimeString()} />
        </Section>
      )}

      <Section title="Decoy Triggers">
        {triggerEvents.length === 0 ? (
          <div style={styles.devEmpty}>No triggers yet</div>
        ) : (
          triggerEvents.slice(0, 5).map((t, i) => (
            <div key={i} style={styles.triggerRow}>
              <span style={styles.triggerKind}>{t.kind}</span>
              <span style={styles.triggerEvent}>{t.event}</span>
              <span style={styles.triggerId}>{t.decoyId.slice(0, 10)}</span>
            </div>
          ))
        )}
      </Section>

      {scoreResponse.watchdog && (
        <Section title="Watchdog (Stage 4)">
          <Row label="action"      value={scoreResponse.watchdog.action} />
          <Row label="trust_score" value={scoreResponse.watchdog.trust_score.toFixed(4)} />
          <Row label="e_rec"       value={scoreResponse.watchdog.e_rec.toFixed(5)} />
          <Row label="confidence"  value={scoreResponse.watchdog.confidence} />
        </Section>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>{title.toUpperCase()}</div>
      {children}
    </div>
  )
}

function Row({ label, value, accent }: { label: string; value: string; accent?: 'danger' | 'warn' | 'green' }) {
  const color = accent === 'danger' ? '#ff3b5c' : accent === 'warn' ? '#ffb800' : accent === 'green' ? '#00ffa3' : '#c9d6e3'
  return (
    <div style={styles.row}>
      <span style={styles.rowLabel}>{label}</span>
      <span style={{ ...styles.rowValue, color }}>{value}</span>
    </div>
  )
}

// ── Inline styles ─────────────────────────────────────────────────────────────

const styles = {
  root: {
    display: 'flex',
    minHeight: '100vh',
    background: '#080b0f',
  } as React.CSSProperties,

  devPanel: {
    width: 300,
    flexShrink: 0,
    background: '#0d1117',
    borderRight: '1px solid #1e2d3d',
    overflowY: 'auto' as const,
  } as React.CSSProperties,

  devInner: {
    padding: 16,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 12,
  } as React.CSSProperties,

  devTitle: {
    fontFamily: 'monospace',
    fontSize: 11,
    fontWeight: 700,
    color: '#ffb800',
    letterSpacing: 1,
  } as React.CSSProperties,

  devNote: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#3a5068',
    letterSpacing: 1,
  } as React.CSSProperties,

  main: (devMode: boolean) => ({
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: devMode ? 'flex-start' : 'center',
    padding: devMode ? 24 : 0,
    overflowY: 'auto' as const,
  } as React.CSSProperties),

  terminalWrap: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: 20,
    padding: 24,
    width: '100%',
    maxWidth: 760,
  } as React.CSSProperties,

  continueBtn: {
    padding: '10px 28px',
    background: '#00e5ff',
    color: '#080b0f',
    border: 'none',
    borderRadius: 4,
    fontFamily: 'monospace',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 2,
    cursor: 'pointer',
  } as React.CSSProperties,

  section: {
    background: '#111820',
    border: '1px solid #1e2d3d',
    borderRadius: 6,
    padding: 10,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 6,
  } as React.CSSProperties,

  sectionTitle: {
    fontFamily: 'monospace',
    fontSize: 8,
    letterSpacing: 2,
    color: '#3a5068',
    marginBottom: 4,
  } as React.CSSProperties,

  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  } as React.CSSProperties,

  rowLabel: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#6b8299',
    letterSpacing: 0.5,
  } as React.CSSProperties,

  rowValue: {
    fontFamily: 'monospace',
    fontSize: 10,
    maxWidth: 160,
    overflow: 'hidden' as const,
    textOverflow: 'ellipsis' as const,
    whiteSpace: 'nowrap' as const,
    textAlign: 'right' as const,
  } as React.CSSProperties,

  devEmpty: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#3a5068',
    textAlign: 'center' as const,
    padding: 6,
  } as React.CSSProperties,

  triggerRow: {
    display: 'flex',
    gap: 8,
    alignItems: 'center',
  } as React.CSSProperties,

  triggerKind: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#ff3b5c',
    width: 52,
    flexShrink: 0,
  } as React.CSSProperties,

  triggerEvent: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#ffb800',
    width: 44,
    flexShrink: 0,
  } as React.CSSProperties,

  triggerId: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#6b8299',
  } as React.CSSProperties,
}
