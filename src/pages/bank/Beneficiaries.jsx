/**
 * Beneficiaries — full payee management + a major behavioral typing surface.
 *  A) Existing beneficiaries (relationship · bank · favorite · last transfer · trust)
 *  B) Add beneficiary (large Description / Transfer Notes / Trust Notes areas)
 *  C) Activity timeline   D) Typing search   E) Quick transfer (prefills Transfers)
 */

import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Field, Input, TextArea, Button, Badge } from '../../components/ui'
import { useBank } from '../../context/BankContext'
import { INR } from '../../data/bankMock'
import s from './bank.module.css'

const RELATIONSHIPS = ['Friend', 'Family', 'Sister', 'Brother', 'Colleague', 'Landlord', 'Vendor', 'Other']
const trustTone = (t) => (t === 'High' ? 'ok' : t === 'Medium' ? 'warn' : 'neutral')

export default function Beneficiaries() {
  const navigate = useNavigate()
  const { beneficiaries: list, addBeneficiary, toggleFavorite, transferLog } = useBank()
  const [query, setQuery] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({
    name: '', nickname: '', relationship: 'Friend', bank: '', account: '', ifsc: '',
    description: '', transferNotes: '', trustNotes: '',
  })

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  const valid = form.name && form.account && form.ifsc

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return list
    return list.filter(b =>
      [b.name, b.nickname, b.relationship, b.bank, b.description, b.transferNotes, b.trustNotes]
        .filter(Boolean).join(' ').toLowerCase().includes(q))
  }, [list, query])

  const toggleFav = (id) => toggleFavorite(id)

  const add = () => {
    if (!valid) return
    addBeneficiary({ ...form, trust: 'Medium' })
    setForm({ name: '', nickname: '', relationship: 'Friend', bank: '', account: '', ifsc: '', description: '', transferNotes: '', trustNotes: '' })
    setShowAdd(false)
  }

  const quickTransfer = (b) => navigate('/app/transfers', {
    state: { prefill: { name: b.name, account: b.account, ifsc: b.ifsc, purpose: '', message: '' } },
  })

  // Activity timeline (C) — synthesized from beneficiaries + transfer log
  const log = transferLog
  const timeline = [
    ...log.slice(0, 4).map(t => ({ t: new Date(t.at).getTime(), text: `Transfer to ${t.name}`, sub: INR(Number(t.amount || 0)) })),
    ...list.slice(0, 4).map(b => ({
      t: b.lastTransfer ? new Date(b.lastTransfer.date).getTime() : 0,
      text: `Last transfer · ${b.name}`, sub: b.lastTransfer ? `${INR(b.lastTransfer.amount)} · ${b.lastTransfer.date}` : 'No transfers yet',
    })),
    { t: 0, text: 'Beneficiary list synced', sub: `${list.length} payees on file` },
  ].sort((a, b) => b.t - a.t)

  return (
    <div className={s.benLayout}>
      <div>
        <div className={s.searchBar}>
          <span>🔍</span>
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search beneficiaries by name, relationship, bank, notes…" />
          <Button size="sm" onClick={() => setShowAdd(v => !v)}>{showAdd ? 'Close' : '+ Add beneficiary'}</Button>
        </div>

        {showAdd && (
          <Card title="Add Beneficiary" sub="These notes are valuable behavioral typing surfaces" className="fade-in">
            <div className={s.formGrid}>
              <Field label="Beneficiary name"><Input value={form.name} onChange={set('name')} placeholder="Harsha Shetty" /></Field>
              <Field label="Nickname"><Input value={form.nickname} onChange={set('nickname')} placeholder="Harsha" /></Field>
              <Field label="Relationship">
                <select value={form.relationship} onChange={set('relationship')} className={s.select}
                  style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', color: 'var(--text)', padding: '11px 13px', fontFamily: 'var(--sans)', fontSize: 14 }}>
                  {RELATIONSHIPS.map(r => <option key={r}>{r}</option>)}
                </select>
              </Field>
              <Field label="Bank name"><Input value={form.bank} onChange={set('bank')} placeholder="HDFC Bank" /></Field>
              <Field label="Account number"><Input value={form.account} onChange={set('account')} placeholder="5521 0098 4412" /></Field>
              <Field label="IFSC"><Input value={form.ifsc} onChange={set('ifsc')} placeholder="HDFC0001234" /></Field>
            </div>
            <Field label="Description" hint="e.g. College friend from diploma. Frequently used for travel expenses.">
              <TextArea value={form.description} onChange={set('description')} placeholder="Who is this person, and how do you usually transact with them?" />
            </Field>
            <Field label="Transfer notes" hint="e.g. Usually receives money for bike rides, food, and trips.">
              <TextArea value={form.transferNotes} onChange={set('transferNotes')} placeholder="What do you typically send them?" />
            </Field>
            <Field label="Trust notes" hint="e.g. Known for 6 years. Personally verified.">
              <TextArea value={form.trustNotes} onChange={set('trustNotes')} placeholder="How well do you know and trust them?" />
            </Field>
            <Button full onClick={add} disabled={!valid}>Save beneficiary</Button>
          </Card>
        )}

        <div className={s.benGrid} style={{ marginTop: showAdd ? 'var(--space-5)' : 0 }}>
          {filtered.map(b => (
            <div key={b.id} className={s.benCard}>
              <div className={s.benHead}>
                <div className={s.benAvatar}>{b.name[0]}</div>
                <div style={{ minWidth: 0 }}>
                  <div className={s.benName}>{b.name}</div>
                  <div className={s.benSub}>{b.nickname ? `“${b.nickname}” · ` : ''}{b.relationship} · {b.bank}</div>
                </div>
                <button className={`${s.star} ${b.favorite ? s.starOn : ''}`} onClick={() => toggleFav(b.id)} title="Favorite">★</button>
              </div>
              <div className={s.benRow}><span>Trust</span><Badge tone={trustTone(b.trust)} dot>{b.trust}</Badge></div>
              <div className={s.benRow}><span>Last transfer</span><span style={{ color: 'var(--text)' }}>{b.lastTransfer ? `${INR(b.lastTransfer.amount)} · ${b.lastTransfer.date}` : '—'}</span></div>
              {b.description && <div className={s.benNotes}>{b.description}</div>}
              <div className={s.benActions}>
                <Button size="sm" full onClick={() => quickTransfer(b)}>Quick transfer →</Button>
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ gridColumn: '1 / -1', textAlign: 'center', color: 'var(--text-3)', padding: 30 }}>No beneficiaries match “{query}”.</div>
          )}
        </div>
      </div>

      <Card title="Activity Timeline" sub="Recent beneficiary & transfer activity">
        <div className={s.tline}>
          {timeline.map((e, i) => (
            <div key={i} className={s.tlineItem}>
              <span className={s.tlineDot} />
              {e.t > 0 && <div className={s.tlineTime}>{new Date(e.t).toLocaleDateString('en-IN')}</div>}
              <div className={s.tlineText}>{e.text}</div>
              <div className={s.tlineSub}>{e.sub}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
