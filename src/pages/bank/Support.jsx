/**
 * Support — banking support center & a major behavioral typing surface.
 * Long-form ticket fields (description, what happened, steps tried, notes) plus
 * a history of previously raised tickets.
 */

import { useState } from 'react'
import { Card, Field, Input, TextArea, Button, Badge } from '../../components/ui'
import { supportTopics, getTickets, addTicket } from '../../data/bankMock'
import s from './bank.module.css'

export default function Support() {
  const [tickets, setTickets] = useState(getTickets())
  const [form, setForm] = useState({
    title: '', category: supportTopics[0], description: '', whatHappened: '', stepsTried: '', additional: '',
  })
  const [done, setDone] = useState(false)

  const set = (k) => (e) => { setForm(f => ({ ...f, [k]: e.target.value })); setDone(false) }
  const valid = form.title.trim() && form.description.trim()

  const submit = () => {
    if (!valid) return
    setTickets(addTicket({ ...form }))
    setForm({ title: '', category: supportTopics[0], description: '', whatHappened: '', stepsTried: '', additional: '' })
    setDone(true)
  }

  return (
    <div className={s.supportGrid}>
      <Card title="Create a Support Ticket" sub="Describe your issue in detail — it helps us resolve faster">
        <Field label="Issue title"><Input value={form.title} onChange={set('title')} placeholder="e.g. UPI payment failed but amount debited" /></Field>

        <Field label="Issue category">
          <div className={s.catChips}>
            {supportTopics.map(t => (
              <button key={t} className={s.chip} onClick={() => setForm(f => ({ ...f, category: t }))}
                style={form.category === t ? { borderColor: 'var(--accent)', color: 'var(--text)', background: 'var(--accent-soft)' } : undefined}>
                {t}
              </button>
            ))}
          </div>
        </Field>

        <Field label="Description" hint="Explain the problem fully.">
          <TextArea value={form.description} onChange={set('description')} placeholder="Describe what went wrong…" style={{ minHeight: 120 }} />
        </Field>
        <Field label="What happened?" hint="Walk us through it step by step.">
          <TextArea value={form.whatHappened} onChange={set('whatHappened')} placeholder="I tried to pay ₹450 via UPI to Swiggy, the app showed success but…" />
        </Field>
        <Field label="Steps already tried" hint="So we don’t repeat them.">
          <TextArea value={form.stepsTried} onChange={set('stepsTried')} placeholder="Restarted the app, checked statement, waited 30 minutes…" />
        </Field>
        <Field label="Additional notes">
          <TextArea value={form.additional} onChange={set('additional')} placeholder="Anything else we should know?" />
        </Field>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button onClick={submit} disabled={!valid}>Submit ticket</Button>
          {done && <Badge tone="ok" dot>Ticket raised</Badge>}
        </div>
      </Card>

      <Card title="Your Tickets" action={<Badge tone="neutral">{tickets.length}</Badge>}>
        {tickets.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-3)', padding: '24px 0', fontSize: 13 }}>
            No tickets yet. Raised tickets will appear here.
          </div>
        )}
        {tickets.map(t => (
          <div key={t.id} className={s.ticketRow}>
            <div className={s.ticketTop}>
              <span className={s.ticketTitle}>{t.title}</span>
              <Badge tone="warn" dot>{t.status}</Badge>
            </div>
            <div className={s.ticketMeta}>{t.id} · {t.category} · {new Date(t.createdAt).toLocaleString('en-IN')}</div>
            {t.description && <div className={s.ticketBody}>{t.description}</div>}
          </div>
        ))}
      </Card>
    </div>
  )
}
