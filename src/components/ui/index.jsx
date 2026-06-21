/**
 * Entropy Bank — UI primitives
 * Shared, theme-aware building blocks used across the new banking + security
 * surfaces. All visuals are driven by the CSS variables in theme/tokens.css.
 */

import s from './ui.module.css'
import { useTheme } from '../../context/ThemeContext'

const cx = (...c) => c.filter(Boolean).join(' ')

const TONE_CLASS = {
  neutral: s.toneNeutral,
  ok:      s.toneOk,
  warn:    s.toneWarn,
  danger:  s.toneDanger,
}
const TONE_COLOR = {
  ok:      'var(--accent)',
  warn:    'var(--warn)',
  danger:  'var(--danger)',
  neutral: 'var(--text-2)',
}

// ── Card ─────────────────────────────────────────────────────────────────────
export function Card({ title, sub, action, children, pad = true, className, ...rest }) {
  return (
    <div className={cx(s.card, className)} {...rest}>
      {(title || action) && (
        <div className={s.cardHead}>
          <div>
            {title && <div className={s.cardTitle}>{title}</div>}
            {sub && <div className={s.cardSub}>{sub}</div>}
          </div>
          {action}
        </div>
      )}
      <div className={pad ? s.cardBody : undefined}>{children}</div>
    </div>
  )
}

// ── StatTile ─────────────────────────────────────────────────────────────────
export function StatTile({ label, value, sub, icon, trend, trendDir = 'up', accent }) {
  return (
    <div className={s.stat}>
      <div className={s.statTop}>
        {icon && <div className={s.statIcon} style={accent ? { background: 'transparent', color: accent } : undefined}>{icon}</div>}
        {trend && (
          <span className={cx(s.trend, trendDir === 'up' ? s.trendUp : s.trendDown)}>
            {trendDir === 'up' ? '▲' : '▼'} {trend}
          </span>
        )}
      </div>
      <div className={s.statValue} style={accent ? { color: accent } : undefined}>{value}</div>
      <div className={s.statLabel}>{label}</div>
      {sub && <div className={s.statSub}>{sub}</div>}
    </div>
  )
}

// ── Button ───────────────────────────────────────────────────────────────────
export function Button({ variant = 'primary', size = 'md', full, children, className, ...rest }) {
  const v = { primary: s.primary, ghost: s.ghost, subtle: s.subtle, danger: s.danger }[variant] || s.primary
  const z = { sm: s.btnSm, md: s.btnMd, lg: s.btnLg }[size] || s.btnMd
  return (
    <button className={cx(s.btn, v, z, full && s.btnFull, className)} {...rest}>{children}</button>
  )
}

// ── Field / Input / TextArea ─────────────────────────────────────────────────
export function Field({ label, hint, children }) {
  return (
    <label className={s.field}>
      {label && <span className={s.fieldLabel}>{label}</span>}
      {children}
      {hint && <span className={s.fieldHint}>{hint}</span>}
    </label>
  )
}
export function Input(props)    { return <input className={s.input} {...props} /> }
export function TextArea(props) { return <textarea className={s.textarea} {...props} /> }

// ── Badge ────────────────────────────────────────────────────────────────────
export function Badge({ tone = 'neutral', dot, children }) {
  return (
    <span className={cx(s.badge, TONE_CLASS[tone])}>
      {dot && <span className={s.badgeDot} />}
      {children}
    </span>
  )
}

// ── ProgressBar ──────────────────────────────────────────────────────────────
export function ProgressBar({ value = 0, tone = 'ok', color }) {
  return (
    <div className={s.barTrack}>
      <div className={s.barFill} style={{ width: `${Math.min(Math.max(value, 0), 1) * 100}%`, background: color || TONE_COLOR[tone] }} />
    </div>
  )
}

// ── MetricBar ────────────────────────────────────────────────────────────────
export function MetricBar({ label, value, unit, fill = 0, tone = 'ok', color }) {
  return (
    <div className={s.metricRow}>
      <div className={s.metricLabel}>{label}</div>
      <ProgressBar value={fill} tone={tone} color={color} />
      <div className={s.metricVal}>{value} {unit && <span>{unit}</span>}</div>
    </div>
  )
}

// ── ProgressRing ─────────────────────────────────────────────────────────────
export function ProgressRing({ value = 0, size = 120, stroke = 9, label, sublabel, color, format }) {
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const v = Math.min(Math.max(value, 0), 1)
  const c = color || (v > 0.7 ? 'var(--accent)' : v > 0.4 ? 'var(--warn)' : 'var(--danger)')
  return (
    <div className={s.ringWrap} style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
        <circle
          cx={size/2} cy={size/2} r={r} fill="none"
          stroke={c} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={circ * (1 - v)}
          transform={`rotate(-90 ${size/2} ${size/2})`}
          style={{ transition: 'stroke-dashoffset .6s var(--ease), stroke .3s' }}
        />
      </svg>
      <div className={s.ringText}>
        <div className={s.ringValue} style={{ fontSize: size * 0.22, color: c }}>
          {format ? format(value) : `${(v * 100).toFixed(0)}`}
        </div>
        {label && <div className={s.ringLabel}>{label}</div>}
        {sublabel && <div className={s.ringLabel} style={{ color: c }}>{sublabel}</div>}
      </div>
    </div>
  )
}

// ── PhaseCard ────────────────────────────────────────────────────────────────
const PHASE_TONE = {
  active: 'var(--accent)', warn: 'var(--warn)', alert: 'var(--danger)', idle: 'var(--text-3)',
}
export function PhaseCard({ n, title, desc, status = 'idle', metric }) {
  const color = PHASE_TONE[status] || PHASE_TONE.idle
  return (
    <div className={s.phase}>
      <div className={s.phaseTopBar} style={{ background: color }} />
      <div className={s.phaseHead}>
        <span className={s.phaseNum}>PHASE {n}</span>
        <span className={s.phaseDot} style={{ background: color, animation: status === 'active' ? 'pulse 2s infinite' : 'none' }} />
      </div>
      <div className={s.phaseTitle}>{title}</div>
      <div className={s.phaseDesc}>{desc}</div>
      {metric && <div className={s.phaseMetric}>{metric}</div>}
      <div className={s.phaseStatus} style={{ color }}>{status}</div>
    </div>
  )
}

// ── ThemeToggle ──────────────────────────────────────────────────────────────
export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  return (
    <div className={s.themeToggle} role="group" aria-label="Theme">
      <span
        className={cx(s.themeOpt, theme === 'dark' && s.themeOptActive)}
        onClick={() => setTheme('dark')} title="Dark" role="button"
      >☾</span>
      <span
        className={cx(s.themeOpt, theme === 'light' && s.themeOptActive)}
        onClick={() => setTheme('light')} title="Light" role="button"
      >☀</span>
    </div>
  )
}

// ── Modal ────────────────────────────────────────────────────────────────────
export function Modal({ open, onClose, title, children, footer }) {
  if (!open) return null
  return (
    <div className={s.overlay} onClick={onClose}>
      <div className={s.modal} onClick={e => e.stopPropagation()}>
        {title && <div className={s.modalHead}><div className={s.modalTitle}>{title}</div></div>}
        <div className={s.modalBody}>{children}</div>
        {footer && <div className={s.modalFoot}>{footer}</div>}
      </div>
    </div>
  )
}
