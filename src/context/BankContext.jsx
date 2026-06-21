/**
 * BankContext.jsx — single source of truth for the (mock) banking layer.
 * --------------------------------------------------------------------------
 * Every banking page reads/writes this one store, so a transfer (or any edit)
 * propagates INSTANTLY everywhere: Dashboard totals, Accounts balances, Recent
 * Transactions, Beneficiary "last transfer", AI Banker balances, and the Money
 * Journal (which auto-logs financial events).
 *
 * Seeded from bankMock + migrated from the older per-key localStorage values,
 * then persisted as one snapshot under `ep_bank_state_v1`. No backend involved.
 */

import { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
import {
  accounts as seedAccounts, transactions as seedTransactions,
  getBeneficiaries, getJournal, getTemplates, getAccountMeta, getTxNotes, getTransferLog, INR,
} from '../data/bankMock'

const BankCtx = createContext(null)
const KEY = 'ep_bank_state_v1'
const clone = (o) => JSON.parse(JSON.stringify(o))
const todayISO = () => new Date().toISOString().slice(0, 10)

function loadState() {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  // First run — migrate from seeds + legacy per-key helpers.
  return {
    accounts:     clone(seedAccounts),
    transactions: clone(seedTransactions),
    beneficiaries: getBeneficiaries(),
    journal:      getJournal(),
    templates:    getTemplates(),
    accountMeta:  getAccountMeta(),
    txNotes:      getTxNotes(),
    transferLog:  getTransferLog(),
  }
}

export function BankProvider({ children }) {
  const [state, setState] = useState(loadState)

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(state)) } catch { /* ignore */ }
  }, [state])

  // ── Derived totals (recomputed from live balances + transactions) ──────────
  const totals = useMemo(() => {
    const net = state.accounts.reduce((s, a) => s + a.balance, 0)
    const savings = state.accounts.filter(a => /sav|deposit/i.test(a.type)).reduce((s, a) => s + a.balance, 0)
    const investments = state.accounts.filter(a => /invest/i.test(a.type)).reduce((s, a) => s + a.balance, 0)
    const monthSpend = state.transactions.filter(t => t.amount < 0).reduce((s, t) => s + Math.abs(t.amount), 0)
    return { net, savings, investments, monthSpend, creditScore: 786 }
  }, [state.accounts, state.transactions])

  // ── Mutations ──────────────────────────────────────────────────────────────
  const transfer = useCallback((p) => {
    const amount = Number(p.amount) || 0
    const fromId = p.fromAccountId || 'ac_chk'
    let ok = true
    setState(prev => {
      const accounts = prev.accounts.map(a => {
        if (a.id !== fromId) return a
        if (a.balance < amount) { ok = false; return a }
        return { ...a, balance: a.balance - amount }
      })
      if (!ok) return prev
      const fromAcct = prev.accounts.find(a => a.id === fromId)
      const txn = {
        id: `t_${Date.now()}`, date: todayISO(),
        merchant: `Transfer → ${p.name}`, category: 'Transfer',
        amount: -amount, method: fromAcct?.name || 'HDFC Savings',
      }
      const beneficiaries = prev.beneficiaries.map(b =>
        b.name === p.name || b.account === p.account
          ? { ...b, lastTransfer: { amount, date: todayISO() } }
          : b)
      const logEntry = { id: `TRF-${Date.now().toString().slice(-6)}`, at: new Date().toISOString(), ...p, amount }
      const journalEntry = {
        id: `j_${Date.now()}`, at: new Date().toISOString(), auto: true,
        prompt: '💸 Financial event',
        body: `Transferred ${INR(amount)} to ${p.name}${p.purpose ? ` · ${p.purpose}` : ''}${p.message ? ` — “${p.message}”` : ''}.`,
      }
      return {
        ...prev,
        accounts,
        transactions: [txn, ...prev.transactions],
        beneficiaries,
        transferLog: [logEntry, ...prev.transferLog],
        journal: [journalEntry, ...prev.journal],
      }
    })
    return ok
  }, [])

  const addBeneficiary = useCallback((b) => {
    setState(prev => ({
      ...prev,
      beneficiaries: [{ id: `b_${Date.now()}`, favorite: false, trust: 'Medium', ...b }, ...prev.beneficiaries],
      journal: [{ id: `j_${Date.now()}`, at: new Date().toISOString(), auto: true, prompt: '👥 Beneficiary added', body: `Added ${b.name}${b.relationship ? ` (${b.relationship})` : ''} as a beneficiary.` }, ...prev.journal],
    }))
  }, [])

  const updateBeneficiaries = useCallback((list) => setState(prev => ({ ...prev, beneficiaries: list })), [])
  const toggleFavorite = useCallback((id) =>
    setState(prev => ({ ...prev, beneficiaries: prev.beneficiaries.map(b => b.id === id ? { ...b, favorite: !b.favorite } : b) })), [])

  const setAccountMeta = useCallback((id, field, value) => {
    setState(prev => ({ ...prev, accountMeta: { ...prev.accountMeta, [id]: { ...(prev.accountMeta[id] || {}), [field]: value } } }))
  }, [])
  const setTxNote = useCallback((id, note) =>
    setState(prev => ({ ...prev, txNotes: { ...prev.txNotes, [id]: note } })), [])

  const addJournalEntry = useCallback((e) =>
    setState(prev => ({ ...prev, journal: [{ id: `j_${Date.now()}`, at: new Date().toISOString(), ...e }, ...prev.journal] })), [])

  const addTemplate = useCallback((t) =>
    setState(prev => ({ ...prev, templates: [{ id: `tpl_${Date.now()}`, ...t }, ...prev.templates].slice(0, 12) })), [])

  const value = {
    ...state,
    totals,
    transfer, addBeneficiary, updateBeneficiaries, toggleFavorite,
    setAccountMeta, setTxNote, addJournalEntry, addTemplate,
  }
  return <BankCtx.Provider value={value}>{children}</BankCtx.Provider>
}

export const useBank = () => {
  const ctx = useContext(BankCtx)
  if (!ctx) throw new Error('useBank must be used within BankProvider')
  return ctx
}
