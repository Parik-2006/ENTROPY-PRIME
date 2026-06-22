/**
 * DeceptionLab — Security Center › Deception Demo Lab.
 *
 * A demonstration-only surface. It drives the REAL backend deception pipeline:
 *   • simulateAttack()  → POST /score        (actual classifier + honeypot routing)
 *   • ShadowEnvView     → GET /api/shadow/*   (actual synthetic environments)
 *
 * Presentation build: the Threat-Intelligence section and all /admin/deception/*
 * polling have been removed. After a launch the lab shows an animated ATTACK
 * PIPELINE plus the rendered attacker environment — no background intervals, no
 * 404s, no console spam.
 *
 * It does NOT touch the production auth/session flow and never runs on its own;
 * an operator must explicitly launch a simulation.
 */

import { useState } from 'react'
import { Card, Button, Badge } from '../../components/ui'
import { ATTACKS, simulateAttack, getShadowEnv } from '../../services/deception'
import AttackPipeline from '../../components/deception/AttackPipeline'
import ShadowEnvView from '../../components/deception/ShadowEnvView'

const THREAT_TONE = { high: 'danger', medium: 'warn', low: 'ok' }

export default function DeceptionLab() {
  const [attackKey, setAttackKey] = useState('credential_stuffing')
  const [launching, setLaunching] = useState(false)
  const [error, setError]   = useState(null)
  const [result, setResult] = useState(null)
  const [env, setEnv]       = useState(null)
  const [view, setView]     = useState('pipeline')

  const attack = ATTACKS[attackKey]

  const launch = async () => {
    setLaunching(true); setError(null); setResult(null); setEnv(null)
    try {
      const res = await simulateAttack(attackKey)
      let envData = null
      if (res.shadow_mode && res.session_token) {
        try { envData = await getShadowEnv(res.session_token) } catch { /* env optional */ }
      }
      setResult(res)
      setEnv(envData)
      setView('pipeline')
    } catch (e) {
      setError(e.message)
    } finally {
      setLaunching(false)
    }
  }

  const envLabel = env?.world || (result?.redirect === '/admin' ? 'shadow_admin' : 'banking')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>Deception Demo Lab</div>
            <div style={{ fontSize: 13, color: 'var(--text-2)' }}>
              Each simulation runs the real classifier and honeypot routing, then renders the attacker's synthetic environment.
            </div>
          </div>
          <Badge tone="warn" dot>demonstration only</Badge>
        </div>
      </Card>

      {/* ── Attack selector ─────────────────────────────────────────────── */}
      <Card title="Attack Simulation" sub="Pick a vector, then launch it through the live pipeline">
        <div style={st.grid}>
          {Object.entries(ATTACKS).map(([key, a]) => (
            <button key={key} onClick={() => setAttackKey(key)}
              style={{ ...st.attackBtn, ...(attackKey === key ? st.attackActive : {}) }}>
              <span style={{ fontSize: 22 }}>{a.icon}</span>
              <span style={st.attackLabel}>{a.label}</span>
              <span style={st.attackExpect}>→ {a.expect}</span>
              <Badge tone={THREAT_TONE[a.threat]}>{a.threat} threat</Badge>
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 16 }}>
          <Button onClick={launch} disabled={launching}>
            {launching ? 'Launching…' : `Launch Simulation — ${attack.label}`}
          </Button>
          {error && <span style={{ color: 'var(--danger)', fontSize: 13 }}>⚠ {error}</span>}
        </div>
      </Card>

      {/* ── Attack Pipeline + attacker environment (replaces Threat Intel) ── */}
      {result && (
        <Card
          title="Attack Pipeline"
          sub={`Classified "${result.attack_class || 'unknown'}" → ${attack.expect}`}
          action={
            <div style={st.tabs}>
              {['pipeline', 'attacker'].map((v) => (
                <button key={v} onClick={() => setView(v)}
                  style={{ ...st.tab, ...(view === v ? st.tabActive : {}) }}>
                  {v === 'pipeline' ? 'Pipeline' : 'Attacker View'}
                </button>
              ))}
            </div>
          }
        >
          {!result.shadow_mode ? (
            <div style={{ color: 'var(--text-2)', fontSize: 13 }}>
              Pipeline did not shadow-route this request (shadow_mode=false). Try a stronger attack vector.
            </div>
          ) : view === 'pipeline' ? (
            <AttackPipeline attack={attack} result={result} env={env} />
          ) : (
            <ShadowEnvView
              token={result.session_token}
              world={envLabel}
              presentation={attack.presentation}
            />
          )}
        </Card>
      )}
    </div>
  )
}

const st = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 },
  attackBtn: { display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 6, padding: '14px 16px', border: '1px solid var(--border)', borderRadius: 12, background: 'var(--surface-2)', cursor: 'pointer', textAlign: 'left' },
  attackActive: { borderColor: 'var(--accent)', boxShadow: '0 0 0 1px var(--accent)' },
  attackLabel: { fontSize: 14, fontWeight: 600, color: 'var(--text)' },
  attackExpect: { fontSize: 11, color: 'var(--text-3)' },
  tabs: { display: 'flex', gap: 6 },
  tab: { padding: '5px 12px', borderRadius: 7, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 },
  tabActive: { background: 'var(--surface-3)', color: 'var(--text)', fontWeight: 600 },
}
