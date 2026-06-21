/**
 * Profile — a major behavioral-collection surface.
 * Rich, multi-section long-form fields that invite 200–500 words of natural
 * writing. Editing is trust-gated: when Identity Confidence collapses to RED,
 * profile edits are blocked (sensitive action) until re-verification.
 */

import { useState } from 'react'
import { Card, Field, Input, TextArea, Button, Badge } from '../../components/ui'
import { useTrust } from '../../context/TrustContext'
import { getProfileDraft, saveProfileDraft } from '../../data/bankMock'
import s from './bank.module.css'

const SECTIONS = [
  { key: 'occupation',         label: 'Occupation',          hint: 'Role, company, what you do.', input: true },
  { key: 'shortBio',           label: 'Short Bio',           hint: 'A few lines about who you are.', full: true },
  { key: 'financialGoals',     label: 'Financial Goals',     hint: 'What are you saving / investing toward?' },
  { key: 'investmentStrategy', label: 'Investment Strategy', hint: 'How you think about risk, SIPs, equity, FDs…' },
  { key: 'monthlyBudget',      label: 'Monthly Budget Notes', hint: 'How you plan and split your monthly spend.' },
  { key: 'lifeGoals',          label: 'Life Goals',          hint: 'Beyond money — what matters to you.' },
  { key: 'futurePurchases',    label: 'Future Purchases',    hint: 'e.g. “Saving for a Triumph Speed 400 and a Goa trip.”' },
  { key: 'emergencyNotes',     label: 'Emergency Contact Notes', hint: 'Who to reach, and context.' },
  { key: 'bankingPreferences', label: 'Additional Banking Preferences', hint: 'Reminders, recurring payments, preferences.' },
]

const countWords = (o) =>
  Object.values(o).reduce((n, v) => n + ((v || '').trim() ? v.trim().split(/\s+/).filter(Boolean).length : 0), 0)

export default function Profile() {
  const { blocked } = useTrust()
  const [form, setForm] = useState(getProfileDraft())
  const [saved, setSaved] = useState(false)

  const set = (k) => (e) => { setForm(f => ({ ...f, [k]: e.target.value })); setSaved(false) }
  const save = () => { saveProfileDraft(form); setSaved(true) }
  const totalWords = countWords(form)

  return (
    <div className={s.grid}>
      <Card>
        <div className={s.saveBar}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ width: 52, height: 52, borderRadius: '50%', display: 'grid', placeItems: 'center', background: 'var(--accent-soft)', color: 'var(--accent)', fontFamily: 'var(--display)', fontWeight: 800, fontSize: 20 }}>
              {(form.fullName || 'P')[0]}
            </div>
            <div>
              <Field label="Full name"><Input value={form.fullName || ''} onChange={set('fullName')} placeholder="Your name" /></Field>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className={s.wordTag}>{totalWords} words written</div>
            <div style={{ marginTop: 8, display: 'flex', gap: 10, alignItems: 'center', justifyContent: 'flex-end' }}>
              {saved && <Badge tone="ok" dot>Saved</Badge>}
              <Button onClick={save} disabled={blocked}>{blocked ? 'Editing locked' : 'Save profile'}</Button>
            </div>
          </div>
        </div>
        {blocked && (
          <div style={{ marginTop: 14, fontSize: 12.5, color: 'var(--danger)' }}>
            🔒 Profile edits are blocked — identity confidence is too low. Re-verify to continue.
          </div>
        )}
      </Card>

      <div className={s.profileGrid}>
        {SECTIONS.map(sec => (
          <div key={sec.key} className={sec.full ? s.profileFull : undefined}>
            <Card title={sec.label} sub={sec.hint}>
              {sec.input ? (
                <Input value={form[sec.key] || ''} onChange={set(sec.key)} disabled={blocked} placeholder={sec.hint} />
              ) : (
                <TextArea value={form[sec.key] || ''} onChange={set(sec.key)} disabled={blocked}
                  placeholder="Write naturally…" style={{ minHeight: sec.full ? 120 : 130 }} />
              )}
            </Card>
          </div>
        ))}
      </div>
    </div>
  )
}
