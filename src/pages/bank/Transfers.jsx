/**
 * Transfers — the highest-value behavioral-signal surface in the demo.
 * Free-typed fields (recipient, account, IFSC, amount, purpose, message, notes)
 * continuously feed the global biometric collectors (PHASE 1/4), and the send
 * is gated by the live Entropy Prime trust score (PHASE 4).
 *
 * Upgrades: purpose presets, message-to-recipient with recent messages, save-as
 * template + favorite beneficiaries quick-pick, transfer history, and prefill
 * from the Beneficiaries "Quick transfer" action (router state).
 */

import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Card, Field, Input, TextArea, Button, Badge, Modal } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { useTrust } from '../../context/TrustContext'
import { useBank } from '../../context/BankContext'
import { INR, transferReasons, recentMessages } from '../../data/bankMock'
import s from './bank.module.css'

const EMPTY = { name: '', account: '', ifsc: '', amount: '', purpose: '', message: '', notes: '', fromAccountId: 'ac_chk' }

function gateState(trust, stable, blocked) {
  if (blocked) return { ok: false, tone: 'danger', title: 'Transfer blocked by Entropy Prime', desc: 'Identity confidence is too low. Re-authentication required.' }
  if (!stable) return { ok: false, tone: 'warn', title: 'Enrollment incomplete', desc: 'Finish behavioral enrollment before sending money.' }
  if (trust < 0.4) return { ok: false, tone: 'danger', title: 'Transfer blocked', desc: 'Identity confidence too low for sensitive actions.' }
  if (trust < 0.7) return { ok: true, tone: 'warn', title: 'Additional verification recommended', desc: 'Trust is moderate — transfer allowed but logged for review.' }
  return { ok: true, tone: 'ok', title: 'Identity verified', desc: 'Entropy Prime confirms this is you. Transfer permitted.' }
}

export default function Transfers() {
  const { trustScore, isProfileStable } = useAuth()
  const { blocked } = useTrust()
  const { accounts, beneficiaries, templates, transferLog, transfer, addTemplate } = useBank()
  const navigate = useNavigate()
  const location = useLocation()

  const [form, setForm] = useState({ ...EMPTY, ...(location.state?.prefill || {}) })
  const [done, setDone] = useState(null)
  const [err, setErr] = useState('')

  // Clear router state after consuming the prefill so a refresh doesn't re-apply.
  useEffect(() => { if (location.state?.prefill) navigate(location.pathname, { replace: true }) }, []) // eslint-disable-line

  const gate = gateState(trustScore, isProfileStable, blocked)
  const set = (k) => (e) => { setForm(f => ({ ...f, [k]: e.target.value })); setErr('') }
  const valid = form.name && form.account && form.ifsc && Number(form.amount) > 0

  const submit = () => {
    if (!gate.ok || !valid) return
    const ok = transfer({ ...form, amount: Number(form.amount) })
    if (!ok) { setErr('Insufficient balance in the selected account.'); return }
    setDone({ ...form })
    setForm(EMPTY)
  }

  const saveTemplate = () => {
    if (!form.name || !form.account) return
    addTemplate({ name: form.name, account: form.account, ifsc: form.ifsc, purpose: form.purpose })
  }
  const applyTemplate = (t) => setForm(f => ({ ...f, name: t.name, account: t.account, ifsc: t.ifsc, purpose: t.purpose || '' }))

  const favorites = beneficiaries.filter(b => b.favorite)
  const history = transferLog

  return (
    <div className={s.transferLayout}>
      <Card title="New Transfer" sub="Send money to any account">
        <div className={s.gateBox} style={{ borderColor: `var(--${gate.tone === 'ok' ? 'accent' : gate.tone})` }}>
          <Badge tone={gate.tone} dot>{(trustScore * 100).toFixed(0)}% trust</Badge>
          <div className={s.gateText}>
            <div className={s.gateTitle}>{gate.title}</div>
            <div className={s.gateDesc}>{gate.desc}</div>
          </div>
        </div>

        {favorites.length > 0 && (
          <Field label="Favorite beneficiaries">
            <div className={s.catChips}>
              {favorites.map(b => (
                <button key={b.id} className={s.chip}
                  onClick={() => setForm(f => ({ ...f, name: b.name, account: b.account, ifsc: b.ifsc }))}>
                  ★ {b.nickname || b.name}
                </button>
              ))}
            </div>
          </Field>
        )}

        <div className={s.formGrid}>
          <div className={s.span2}>
            <Field label="From account">
              <select className={s.select} value={form.fromAccountId} onChange={set('fromAccountId')}>
                {accounts.map(a => <option key={a.id} value={a.id}>{a.name} · {a.number} · {INR(a.balance)}</option>)}
              </select>
            </Field>
          </div>
          <div className={s.span2}><Field label="Recipient name"><Input value={form.name} onChange={set('name')} placeholder="e.g. Vedanth Kumar" /></Field></div>
          <Field label="Account number"><Input value={form.account} onChange={set('account')} placeholder="5521 0098 4412" /></Field>
          <Field label="IFSC code"><Input value={form.ifsc} onChange={set('ifsc')} placeholder="HDFC0001234" /></Field>
          <Field label="Amount (₹)"><Input type="number" value={form.amount} onChange={set('amount')} placeholder="2500" /></Field>
          <Field label="Purpose">
            <select className={s.select} value={form.purpose} onChange={set('purpose')}>
              <option value="">Select a reason…</option>
              {transferReasons.map(r => <option key={r}>{r}</option>)}
            </select>
          </Field>
        </div>

        <Field label="Message to recipient" hint="Tap a recent message or write your own.">
          <Input value={form.message} onChange={set('message')} placeholder="Here’s your share for the trip 🌴" />
          <div className={s.catChips} style={{ marginTop: 8 }}>
            {recentMessages.map(m => (
              <button key={m} className={s.chip} onClick={() => setForm(f => ({ ...f, message: m }))}>{m}</button>
            ))}
          </div>
        </Field>

        <Field label="Personal transfer notes" hint="Private — for your own records.">
          <TextArea value={form.notes} onChange={set('notes')} placeholder="Why this transfer, relationship context, anything to remember…" />
        </Field>

        {err && <div style={{ color: 'var(--danger)', fontSize: 12.5, marginBottom: 10 }}>{err}</div>}
        <div style={{ display: 'flex', gap: 10 }}>
          <Button variant="ghost" onClick={saveTemplate} disabled={!form.name || !form.account}>Save as template</Button>
          <Button full size="lg" onClick={submit} disabled={!gate.ok || !valid}>
            {gate.ok ? `Send ${form.amount ? INR(Number(form.amount)) : 'transfer'} →` : 'Transfer locked'}
          </Button>
        </div>
      </Card>

      <div className={s.grid}>
        {templates.length > 0 && (
          <Card title="Templates" sub="Saved transfer recipients">
            <div className={s.catChips}>
              {templates.map(t => (
                <button key={t.id} className={s.chip} onClick={() => applyTemplate(t)}>{t.name}{t.purpose ? ` · ${t.purpose}` : ''}</button>
              ))}
            </div>
          </Card>
        )}

        <Card title="Transfer History" action={<Badge tone="neutral">{history.length}</Badge>}>
          {history.length === 0 && <div style={{ color: 'var(--text-3)', fontSize: 13, padding: '14px 0', textAlign: 'center' }}>No transfers yet.</div>}
          {history.slice(0, 8).map(h => (
            <div key={h.id} className={s.histRow}>
              <div>
                <div className={s.histName}>{h.name}</div>
                <div className={s.histMeta}>{h.id} · {new Date(h.at).toLocaleString('en-IN')}{h.purpose ? ` · ${h.purpose}` : ''}</div>
              </div>
              <span style={{ fontFamily: 'var(--mono)', color: 'var(--text)' }}>{INR(Number(h.amount || 0))}</span>
            </div>
          ))}
        </Card>

        <Card title="How this is protected" sub="Behind every keystroke">
          <p style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.6 }}>
            As you fill this form, Entropy Prime measures your typing rhythm (PHASE 1) and the send is
            gated by your live trust score (PHASE 4). Bots collapse the humanity score and are
            shadow-routed (PHASE 3).
          </p>
        </Card>
      </div>

      <Modal open={!!done} title="✓ Transfer submitted" footer={<Button onClick={() => setDone(null)}>Done</Button>}>
        {done && (
          <>
            <p>You sent <strong>{INR(Number(done.amount))}</strong> to <strong>{done.name}</strong> ({done.account}).</p>
            {done.message && <p style={{ marginTop: 8 }}>Message: “{done.message}”</p>}
            <p style={{ marginTop: 10, color: 'var(--text-3)' }}>Verified and authorized by Entropy Prime · trust {(trustScore * 100).toFixed(0)}%.</p>
          </>
        )}
      </Modal>
    </div>
  )
}
