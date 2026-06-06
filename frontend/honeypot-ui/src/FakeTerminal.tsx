/**
 * src/FakeTerminal.tsx — Shadow-mode fake terminal UI.
 *
 * Shown to bots that have been shadow-routed (shadow_mode=true in /score).
 * Renders plausible-looking "admin terminal" output that a bot might
 * interpret as a real backend, buying time for MAB reward collection.
 *
 * Props are minimal — the component self-animates using local state.
 * The session_token displayed is the synthetic shadow token from /score,
 * not a real session token.
 */

import React, { useEffect, useRef, useState } from 'react'
import type { ScoreResponse } from './types'
import { ARM_LABELS } from './types'

interface FakeTerminalProps {
  scoreResponse: ScoreResponse
  onMabRewardReady?: (arm: number) => void
}

// Lines of plausible-looking output rendered with a typing animation
function buildTerminalLines(res: ScoreResponse): string[] {
  const token = res.session_token
  const arm   = res.mab_arm ?? 0
  const armLabel = ARM_LABELS[arm] ?? `Arm ${arm}`
  const now   = new Date().toISOString()

  return [
    `[${now}] ENTROPY PRIME v3.2 — Auth Gateway`,
    `> Initializing pipeline...`,
    `  Stage 1 (Biometric)   θ=${res.humanity_score.toFixed(4)}  conf=${res.pipeline_confidence}`,
    `  Stage 2 (Honeypot)    shadow_mode=TRUE  arm=${arm} (${armLabel})`,
    `  Stage 3 (Governor)    preset=${res.action_label}  degraded=${res.degraded}`,
    `  Stage 4 (Watchdog)    ${res.watchdog ? `action=${res.watchdog.action}  trust=${res.watchdog.trust_score.toFixed(3)}` : 'skipped (no latent vector)'}`,
    ``,
    `> Session provisioned:`,
    `  token=${token}`,
    `  expires_in=1800s`,
    `  argon2_params  m=${res.argon2_params.m}  t=${res.argon2_params.t}  p=${res.argon2_params.p}`,
    ``,
    `> Shadow sandbox ACTIVE — MAB deception strategy: ${armLabel}`,
    `> All API responses will be synthetic.`,
    `> Press Ctrl+C to exit (just kidding).`,
  ]
}

export function FakeTerminal({ scoreResponse, onMabRewardReady }: FakeTerminalProps) {
  const [visibleLines, setVisibleLines] = useState<string[]>([])
  const [cursor, setCursor]             = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  const lines = buildTerminalLines(scoreResponse)

  // Animate lines appearing one by one
  useEffect(() => {
    let i = 0
    const interval = setInterval(() => {
      if (i >= lines.length) {
        clearInterval(interval)
        // Signal that enough time has passed to collect MAB reward
        const arm = scoreResponse.mab_arm ?? 0
        onMabRewardReady?.(arm)
        return
      }
      setVisibleLines((prev) => [...prev, lines[i]])
      i++
    }, 90)
    return () => clearInterval(interval)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Blinking cursor
  useEffect(() => {
    const id = setInterval(() => setCursor((v) => !v), 530)
    return () => clearInterval(id)
  }, [])

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [visibleLines])

  return (
    <div style={styles.terminal}>
      <div style={styles.titleBar}>
        <span style={styles.titleDot('red')} />
        <span style={styles.titleDot('yellow')} />
        <span style={styles.titleDot('green')} />
        <span style={styles.titleText}>entropy-prime — bash</span>
      </div>
      <div style={styles.body}>
        {visibleLines.map((line, idx) => (
          <div key={idx} style={styles.line(line)}>
            {line || '\u00a0'}
          </div>
        ))}
        {visibleLines.length < lines.length && (
          <div style={styles.line('')}>
            <span style={{ color: '#00e5ff' }}>{'> '}</span>
            <span style={{ color: cursor ? '#00ffa3' : 'transparent' }}>█</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Inline styles ─────────────────────────────────────────────────────────────

const styles = {
  terminal: {
    background: '#0d1117',
    border: '1px solid #1e2d3d',
    borderRadius: 8,
    fontFamily: "'Space Mono', 'Courier New', monospace",
    fontSize: 12,
    overflow: 'hidden',
    boxShadow: '0 4px 32px rgba(0,0,0,0.8)',
    maxWidth: 720,
    width: '100%',
  } as React.CSSProperties,

  titleBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '8px 14px',
    background: '#111820',
    borderBottom: '1px solid #1e2d3d',
  } as React.CSSProperties,

  titleDot: (color: 'red' | 'yellow' | 'green') => ({
    width: 12, height: 12, borderRadius: '50%',
    background: { red: '#ff5f57', yellow: '#febc2e', green: '#28c840' }[color],
    display: 'inline-block',
  } as React.CSSProperties),

  titleText: {
    marginLeft: 8,
    color: '#6b8299',
    fontSize: 11,
    letterSpacing: 1,
  } as React.CSSProperties,

  body: {
    padding: '16px 18px',
    minHeight: 240,
    maxHeight: 480,
    overflowY: 'auto' as const,
  } as React.CSSProperties,

  line: (text: string) => ({
    color: text.startsWith('>') ? '#00e5ff'
         : text.startsWith('  Stage') ? '#c9d6e3'
         : text.startsWith('  ') ? '#6b8299'
         : '#c9d6e3',
    lineHeight: 1.7,
    whiteSpace: 'pre' as const,
  } as React.CSSProperties),
}
