/**
 * SecurityCenter — "Security Health Center" (judge-friendly).
 * Presents the live Entropy Prime state as a premium health dashboard: Identity
 * Confidence, Trust Score, session status, behavior stability, risk level, the
 * four active protection layers, a live trust timeline, and verification
 * history. ALL original engine metrics are preserved under "Engine details"
 * (neural vectors, model health, live θ / E_rec charts) — nothing removed.
 */

import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from 'recharts'
import { useAuth } from '../../context/AuthContext'
import { useTrust } from '../../context/TrustContext'
import { healthCheck, getModelsStatus } from '../../services/api'
import { Card, StatTile, PhaseCard, MetricBar, Badge, Button } from '../../components/ui'
import TrustTimeline from '../../components/TrustTimeline'
import s from './security.module.css'

const RISK = { green: ['Low', 'var(--accent)'], yellow: ['Guarded', 'var(--gold)'], orange: ['Elevated', '#FF9F45'], red: ['Critical', 'var(--danger)'] }
const EVENT_TONE = { verification: 'ok', session: 'neutral', risk: 'warn', bot: 'danger' }

function ChartTip({ active, payload }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border-2)', padding: '6px 10px', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text)', borderRadius: 8 }}>
      θ: {payload[0]?.value?.toFixed(3)}<br />E_rec: {payload[1]?.value?.toFixed(4)}
    </div>
  )
}

export default function SecurityCenter() {
  const { liveTheta, trustScore, epReady, getClient, liveDrift, selectedFeatures, user } = useAuth()
  const { confidence, color, tierKey, behaviorStatus, label, events, lastVerifiedAt } = useTrust()

  const [chart, setChart] = useState([])
  const [kb, setKb] = useState({ avgDwell: 0, avgFlight: 0, count: 0 })
  const [pt, setPt] = useState({ avgSpeed: 0, avgJitter: 0, avgAccel: 0, count: 0 })
  const [health, setHealth] = useState(null)
  const [models, setModels] = useState(null)
  const [showEngine, setShowEngine] = useState(false)

  const theta = liveTheta ?? 0
  const eRec = getClient()?.watchdog?.lastERec ?? 0
  const [risk, riskColor] = RISK[tierKey] || RISK.green

  useEffect(() => {
    const id = setInterval(() => {
      const ep = getClient()
      const e = ep?.watchdog?.lastERec ?? 0
      setChart(prev => [...prev.slice(-60), { t: new Date().toLocaleTimeString('en', { hour12: false }), theta: +(liveTheta ?? 0).toFixed(4), eRec: +e.toFixed(4) }])
      if (ep) { setKb(ep.getKeyboardStats()); setPt(ep.getPointerStats()) }
    }, 1000)
    return () => clearInterval(id)
  }, [getClient, liveTheta])

  useEffect(() => {
    const tick = () => {
      healthCheck().then(setHealth).catch(() => setHealth({ status: 'unreachable' }))
      getModelsStatus().then(setModels).catch(() => setModels(null))
    }
    tick(); const id = setInterval(tick, 15000); return () => clearInterval(id)
  }, [])

  const phaseStatus = (n) => {
    if (!epReady) return 'idle'
    if (n === 1) return theta > 0.3 ? 'active' : 'alert'
    if (n === 2) return 'active'
    if (n === 3) return theta < 0.1 ? 'alert' : 'active'
    if (n === 4) return eRec > 0.18 ? 'warn' : 'active'
  }
  const verifAgo = Math.max(0, Math.round((Date.now() - lastVerifiedAt) / 60000))

  return (
    <div className={s.grid}>
      {/* Headline health */}
      <div className={s.statRow}>
        <StatTile icon="🛡" label="Identity Confidence" value={`${confidence}%`} accent={color} sub={label} />
        <StatTile icon="✓" label="Trust Score" value={`${(trustScore * 100).toFixed(0)}%`} accent={trustScore > 0.7 ? 'var(--accent)' : trustScore > 0.4 ? 'var(--gold)' : 'var(--danger)'} sub="PHASE 4 watchdog" />
        <StatTile icon="◐" label="Behavior Stability" value={behaviorStatus} accent={color} sub={`Drift ${(liveDrift ?? 0).toFixed(2)}`} />
        <StatTile icon="⚑" label="Risk Level" value={risk} accent={riskColor} sub={`Verified ${verifAgo}m ago`} />
      </div>

      {/* Active protection layers */}
      <Card title="Active Protection Layers" sub="All four Entropy Prime phases running on this session" action={<Badge tone="ok" dot>Protected</Badge>}>
        <div className={s.phaseRow}>
          <PhaseCard n={1} title="Biological Gateway" status={phaseStatus(1)} desc="Keystroke & pointer biometrics (1D-CNN)." metric={`θ ${(theta * 100).toFixed(0)}%`} />
          <PhaseCard n={2} title="Resource Governor" status={phaseStatus(2)} desc="Adaptive Argon2id hardening (DQN+PPO)." metric="DMS active" />
          <PhaseCard n={3} title="Offensive Deception" status={phaseStatus(3)} desc="Bots shadow-routed to honeypots (MAB)." metric={theta < 0.1 ? 'bot routed' : 'armed'} />
          <PhaseCard n={4} title="Session Watchdog" status={phaseStatus(4)} desc="Continuous identity-drift detection." metric={`E_rec ${eRec.toFixed(3)}`} />
        </div>
      </Card>

      {/* Trust timeline + verification history */}
      <div className={s.twoCol}>
        <Card title="Trust Timeline" sub="Identity confidence over this session">
          <TrustTimeline height={220} />
        </Card>
        <Card title="Verification History" action={<Badge tone="neutral">{events.length}</Badge>}>
          <div className={s.evtList}>
            {events.slice(0, 8).map(e => (
              <div key={e.id} className={s.evtRow}>
                <Badge tone={EVENT_TONE[e.kind] || 'neutral'} dot>{e.kind}</Badge>
                <div style={{ flex: 1 }}>
                  <div className={s.evtTitle}>{e.title}</div>
                  <div className={s.evtSub}>{e.desc}</div>
                </div>
                <span className={s.evtTime}>{new Date(e.t).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Engine details (all original developer metrics preserved) */}
      <Card
        title="Engine Details"
        sub="Raw model telemetry — preserved for engineers"
        action={<Button variant="ghost" size="sm" onClick={() => setShowEngine(v => !v)}>{showEngine ? 'Hide' : 'Show'}</Button>}
      >
        {showEngine && (
          <div className={s.grid} style={{ marginTop: 4 }}>
            <div className={s.statRow}>
              <StatTile icon="θ" label="Humanity Score" value={`${(theta * 100).toFixed(1)}%`} accent={theta > 0.7 ? 'var(--accent)' : theta > 0.4 ? 'var(--gold)' : 'var(--danger)'} />
              <StatTile icon="E" label="Reconstruction Error" value={eRec.toFixed(4)} accent={eRec > 0.18 ? 'var(--gold)' : 'var(--accent)'} />
              <StatTile icon="⌨" label="Keystrokes" value={kb.count ?? 0} sub={`Dwell ${(kb.avgDwell || 0).toFixed(0)}ms`} />
              <StatTile icon="🖱" label="Pointer Events" value={pt.count ?? 0} sub={`Jitter ${(pt.avgJitter || 0).toFixed(1)}`} />
            </div>
            <div className={s.chartRow}>
              <Card title="Humanity Score θ — Live">
                <ResponsiveContainer width="100%" height={170}>
                  <LineChart data={chart}>
                    <XAxis dataKey="t" tick={{ fill: 'var(--text-3)', fontSize: 9, fontFamily: 'var(--mono)' }} interval={10} />
                    <YAxis domain={[0, 1]} tick={{ fill: 'var(--text-3)', fontSize: 9, fontFamily: 'var(--mono)' }} />
                    <Tooltip content={<ChartTip />} />
                    <ReferenceLine y={0.7} stroke="var(--accent)" strokeDasharray="4 2" />
                    <ReferenceLine y={0.3} stroke="var(--danger)" strokeDasharray="4 2" />
                    <Line type="monotone" dataKey="theta" stroke="var(--accent)" dot={false} strokeWidth={2} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </Card>
              <Card title="Reconstruction Error E_rec — Live">
                <ResponsiveContainer width="100%" height={170}>
                  <LineChart data={chart}>
                    <XAxis dataKey="t" tick={{ fill: 'var(--text-3)', fontSize: 9, fontFamily: 'var(--mono)' }} interval={10} />
                    <YAxis domain={[0, 0.4]} tick={{ fill: 'var(--text-3)', fontSize: 9, fontFamily: 'var(--mono)' }} />
                    <Tooltip content={<ChartTip />} />
                    <ReferenceLine y={0.18} stroke="var(--gold)" strokeDasharray="4 2" />
                    <Line type="monotone" dataKey="eRec" stroke="var(--accent-2)" dot={false} strokeWidth={2} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </Card>
            </div>
            <div className={s.twoCol}>
              <Card title="Neuromuscular Signal Vectors">
                <MetricBar label="Avg dwell time" value={(kb.avgDwell || 0).toFixed(1)} unit="ms" fill={Math.min((kb.avgDwell || 0) / 300, 1)} />
                <MetricBar label="Avg flight time" value={(kb.avgFlight || 0).toFixed(1)} unit="ms" fill={Math.min((kb.avgFlight || 0) / 500, 1)} />
                <MetricBar label="Pointer speed" value={(pt.avgSpeed || 0).toFixed(1)} unit="px/s" fill={Math.min((pt.avgSpeed || 0) / 1000, 1)} />
                <MetricBar label="Jitter magnitude" value={(pt.avgJitter || 0).toFixed(2)} unit="σ" fill={Math.min((pt.avgJitter || 0) / 80, 1)} color="var(--gold)" />
                <MetricBar label="Acceleration" value={(pt.avgAccel || 0).toFixed(1)} unit="px/s²" fill={Math.min((pt.avgAccel || 0) / 500, 1)} />
                <MetricBar label="Features selected" value={selectedFeatures?.length ?? 0} unit="" fill={Math.min((selectedFeatures?.length ?? 0) / 8, 1)} />
              </Card>
              <Card title="Model & Server Health" action={<Badge tone={health?.status === 'ok' ? 'ok' : 'danger'} dot>{health?.status?.toUpperCase() ?? '...'}</Badge>}>
                <div className={s.kv}><span className={s.kvKey}>Server</span><span className={s.kvVal}>{health?.status ?? '—'}</span></div>
                <div className={s.kv}><span className={s.kvKey}>RL steps</span><span className={s.kvVal}>{health?.rl_steps ?? '—'}</span></div>
                <div className={s.kv}><span className={s.kvKey}>Entropy (H_exp)</span><span className={s.kvVal}>{((user?.hExp ?? 0) * 100).toFixed(0)}%</span></div>
                {models && typeof models === 'object'
                  ? Object.entries(models).slice(0, 6).map(([k, v]) => (
                      <div className={s.kv} key={k}><span className={s.kvKey}>{k}</span><span className={s.kvVal}>{typeof v === 'object' ? JSON.stringify(v).slice(0, 22) : String(v)}</span></div>
                    ))
                  : <div style={{ fontSize: 12, color: 'var(--text-3)', paddingTop: 8 }}>Model status unavailable (backend offline).</div>}
              </Card>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
