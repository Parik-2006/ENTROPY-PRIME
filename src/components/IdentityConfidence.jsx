/**
 * IdentityConfidence — the always-on, top-right "Identity Confidence" widget.
 * Compact animated dial + percentage that visibly reacts as behavior changes.
 * Click to expand a popover with Trust Score, Behavior Status, Last Verification
 * and Session Duration (P7).
 */

import { useState, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useTrust } from '../context/TrustContext'
import { Badge } from './ui'
import s from './trust.module.css'

function ago(ts) {
  const sec = Math.floor((Date.now() - ts) / 1000)
  if (sec < 60) return `${sec}s ago`
  const m = Math.floor(sec / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}
function dur(ts) {
  const sec = Math.floor((Date.now() - ts) / 1000)
  const m = Math.floor(sec / 60), sS = sec % 60
  return m > 0 ? `${m}m ${sS}s` : `${sS}s`
}

export default function IdentityConfidence() {
  const { confidence, color, label, tierKey, trustScore, behaviorStatus, lastVerifiedAt, sessionStart } = useTrust()
  const [open, setOpen] = useState(false)
  const [, tick] = useState(0)
  useEffect(() => { const id = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(id) }, [])

  const r = 16, circ = 2 * Math.PI * r, v = confidence / 100

  return (
    <div className={s.widgetWrap}>
      <div className={s.widget} style={{ borderColor: tierKey === 'green' ? 'var(--border-2)' : color }} onClick={() => setOpen(o => !o)}>
        <div className={s.dial}>
          <svg width="38" height="38">
            <circle cx="19" cy="19" r={r} fill="none" stroke="var(--surface-3)" strokeWidth="3" />
            <motion.circle cx="19" cy="19" r={r} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
              transform="rotate(-90 19 19)" strokeDasharray={circ}
              animate={{ strokeDashoffset: circ * (1 - v) }} transition={{ duration: 0.5, ease: 'easeOut' }} />
          </svg>
          <span className={`${s.dialText} ${tierKey !== 'green' ? s.pulse : ''}`} style={{ color }}>{confidence}</span>
        </div>
        <div>
          <div className={s.wLabel}>Identity Confidence</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
            <motion.span key={confidence} className={s.wValue} style={{ color }}
              initial={{ opacity: 0.5, y: -2 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
              {confidence}%
            </motion.span>
            <span className={s.wState} style={{ color }}>{label}</span>
          </div>
        </div>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div className={s.popover}
            initial={{ opacity: 0, y: -8, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }} transition={{ duration: 0.18 }}>
            <div className={s.popHead}>
              <span className={s.popTitle} style={{ color }}>{confidence}% confident</span>
              <Badge tone={tierKey === 'green' ? 'ok' : tierKey === 'red' ? 'danger' : 'warn'} dot>{label}</Badge>
            </div>
            <div className={s.popRow}><span className={s.popKey}>Identity confidence</span><span className={s.popVal} style={{ color }}>{confidence}%</span></div>
            <div className={s.popRow}><span className={s.popKey}>Trust score</span><span className={s.popVal}>{Math.round((trustScore ?? 1) * 100)}%</span></div>
            <div className={s.popRow}><span className={s.popKey}>Behavior status</span><span className={s.popVal}>{behaviorStatus}</span></div>
            <div className={s.popRow}><span className={s.popKey}>Last verification</span><span className={s.popVal}>{ago(lastVerifiedAt)}</span></div>
            <div className={s.popRow}><span className={s.popKey}>Session duration</span><span className={s.popVal}>{dur(sessionStart)}</span></div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
