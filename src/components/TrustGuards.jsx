/**
 * TrustGuards — the visible consequences of the 4-tier trust model.
 *   <TrustBanner/>  yellow non-blocking deviation warning
 *   <TrustModal/>   orange quick-verification / red block + re-authentication
 *
 * Rendered globally inside AppShell so every page is protected consistently.
 */

import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useTrust } from '../context/TrustContext'
import { useAuth } from '../context/AuthContext'
import { Button, Field, Input } from './ui'
import s from './trust.module.css'

export function TrustBanner() {
  const { tierKey, confidence } = useTrust()
  const show = tierKey === 'yellow'
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          className={s.banner}
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
        >
          <span className={s.bannerIcon}>⚠️</span>
          <span className={s.bannerText}>
            <b>Behavior deviation detected.</b> Your interaction pattern shifted slightly —
            Entropy Prime is continuously monitoring this session (confidence {confidence}%).
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function TrustModal() {
  const { needsVerify, blocked, confidence, color, verifyIdentity } = useTrust()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState(user?.email ?? '')
  const [password, setPassword] = useState('')

  const open = needsVerify || blocked
  const reauth = () => { logout(); navigate('/login') }

  return (
    <AnimatePresence>
      {open && (
        <div className={s.overlay}>
          <motion.div
            className={s.sheet}
            initial={{ opacity: 0, scale: 0.94, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 260, damping: 24 }}
          >
            <div className={s.sheetTop} style={{ background: color }} />
            <div className={s.sheetBody}>
              <div className={s.sheetIcon} style={{ background: 'var(--danger-soft)', color }}>
                {blocked ? '🔒' : '🛡️'}
              </div>
              <div className={s.sheetTitle}>
                {blocked ? 'Identity not verified' : 'Identity confidence reduced'}
              </div>
              <div className={s.sheetDesc}>
                {blocked
                  ? 'Entropy Prime can no longer confirm this is the account owner. Sensitive actions — transfers, beneficiary changes and profile edits — are blocked until you re-authenticate.'
                  : 'Entropy Prime detected a significant change in interaction behavior on this session. This is a quick check — no need to log out. Confirm your identity to continue.'}
              </div>

              <div className={s.metaPill}>
                <span style={{ width: 8, height: 8, borderRadius: 999, background: color, display: 'inline-block' }} />
                Identity Confidence&nbsp;<b style={{ color }}>{confidence}%</b>
              </div>

              {!blocked && (
                <div className={s.formGap}>
                  <Field label="Email">
                    <Input value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
                  </Field>
                  <Field label="Password">
                    <Input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />
                  </Field>
                </div>
              )}

              <div className={s.sheetActions}>
                {blocked ? (
                  <>
                    <Button variant="ghost" full onClick={verifyIdentity}>It’s me — quick verify</Button>
                    <Button variant="danger" full onClick={reauth}>Re-authenticate</Button>
                  </>
                ) : (
                  <>
                    <Button variant="ghost" onClick={reauth}>Full re-login</Button>
                    <Button full onClick={verifyIdentity} disabled={!email || !password}>Verify identity</Button>
                  </>
                )}
              </div>

              <div className={s.note}>
                Same device · same session · correct password — yet the behavioral signature changed.
                This is Entropy Prime’s continuous authentication (PHASE 4) in action.
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
