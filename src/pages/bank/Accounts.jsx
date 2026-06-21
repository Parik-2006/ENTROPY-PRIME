/**
 * Accounts — account overview with editable behavioral surfaces:
 * account nicknames, savings/investment goal notes, per-transaction notes,
 * a typing-enabled transaction search, and derived financial insights.
 */

import { useState, useMemo } from 'react'
import { Card, Input, TextArea, Badge } from '../../components/ui'
import { useBank } from '../../context/BankContext'
import { INR } from '../../data/bankMock'
import s from './bank.module.css'

const goalLabel = (type) =>
  type === 'Investment' ? 'Investment goal notes' : type === 'Savings' ? 'Savings goal notes' : 'Account goal notes'

const INSIGHTS = [
  ['📈', 'Your savings rate is 38% this month — above your 30% target. Nicely done.'],
  ['🍽', 'Food & Dining is your fastest-growing category (+18%). A small trim frees ~₹3,500/month.'],
  ['💡', 'Two subscriptions worth ₹998/month look unused — consider cancelling.'],
  ['🎯', 'At your current pace you’ll hit the ₹2,00,000 bike goal in ~5 months.'],
]

export default function Accounts() {
  const { accounts, transactions, accountMeta: meta, txNotes, setAccountMeta, setTxNote } = useBank()
  const [query, setQuery] = useState('')

  const setMetaField = (id, field, value) => setAccountMeta(id, field, value)
  const setNote = (id, value) => setTxNote(id, value)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return transactions
    return transactions.filter(t => `${t.merchant} ${t.category} ${t.method}`.toLowerCase().includes(q))
  }, [query, transactions])

  return (
    <div className={s.grid}>
      <div className={s.statRow}>
        {accounts.map(a => (
          <div key={a.id} className={s.acctCard}>
            <div className={s.acctBar} style={{ background: a.accent }} />
            <div className={s.acctType}>{a.type} · {a.bank}</div>
            <div className={s.acctName}>{meta[a.id]?.nickname || a.name}</div>
            <div className={s.acctNum}>{a.number}</div>
            <div className={s.acctBal}>{INR(a.balance)}</div>
            <input className={s.noteInput} placeholder="Account nickname…"
              value={meta[a.id]?.nickname || ''} onChange={e => setMetaField(a.id, 'nickname', e.target.value)} />
            <textarea className={s.noteInput} style={{ minHeight: 60, marginTop: 8 }}
              placeholder={`${goalLabel(a.type)}…`}
              value={meta[a.id]?.goalNotes || ''} onChange={e => setMetaField(a.id, 'goalNotes', e.target.value)} />
          </div>
        ))}
      </div>

      <div className={s.twoCol}>
        <Card title="Transaction History"
          action={<div className={s.searchBar} style={{ margin: 0, width: 240, padding: '6px 12px' }}>
            <span>🔍</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search transactions…" />
          </div>}>
          <div className={s.txList}>
            {filtered.map(t => (
              <div key={t.id} style={{ borderBottom: '1px solid var(--border)', padding: '12px 0' }}>
                <div className={s.txRow} style={{ borderBottom: 'none', padding: 0 }}>
                  <div className={s.txIcon}>{t.amount > 0 ? '↓' : '↑'}</div>
                  <div>
                    <div className={s.txMerchant}>{t.merchant}</div>
                    <div className={s.txMeta}>{t.date} · {t.category} · {t.method}</div>
                  </div>
                  <div className={`${s.txAmt} ${t.amount > 0 ? s.amtIn : s.amtOut}`}>
                    {t.amount > 0 ? '+' : '−'}{INR(Math.abs(t.amount))}
                  </div>
                </div>
                <input className={s.noteInput} placeholder="Add a note to this transaction…"
                  value={txNotes[t.id] || ''} onChange={e => setNote(t.id, e.target.value)} />
              </div>
            ))}
            {filtered.length === 0 && <div style={{ textAlign: 'center', color: 'var(--text-3)', padding: 24 }}>No transactions match “{query}”.</div>}
          </div>
        </Card>

        <Card title="Recent Financial Insights" action={<Badge tone="ok" dot>AI</Badge>}>
          {INSIGHTS.map(([icon, text], i) => (
            <div key={i} className={s.insight}>
              <span className={s.insightIcon}>{icon}</span>
              <span className={s.insightText}>{text}</span>
            </div>
          ))}
        </Card>
      </div>
    </div>
  )
}
