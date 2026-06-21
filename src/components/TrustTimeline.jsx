/**
 * TrustTimeline — live "Identity Confidence over time" area chart.
 * Reads the shared history from TrustContext so the Dashboard and Security
 * Center show the exact same trust journey (critical for the demo narrative:
 * user changes → trust changes → verification triggers).
 */

import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from 'recharts'
import { useTrust } from '../context/TrustContext'

const fmt = (t) => new Date(t).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })

function Tip({ active, payload }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border-2)', padding: '6px 10px', borderRadius: 8, fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text)' }}>
      {fmt(payload[0].payload.t)} · <b>{payload[0].value}%</b>
    </div>
  )
}

export default function TrustTimeline({ height = 200 }) {
  const { history, color } = useTrust()
  const data = history.length > 1 ? history : [{ t: Date.now() - 1000, c: 100 }, ...history]

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="trustFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <XAxis dataKey="t" tickFormatter={fmt} tick={{ fill: 'var(--text-3)', fontSize: 9, fontFamily: 'var(--mono)' }} minTickGap={40} />
        <YAxis domain={[0, 100]} tick={{ fill: 'var(--text-3)', fontSize: 9, fontFamily: 'var(--mono)' }} />
        <Tooltip content={<Tip />} />
        <ReferenceLine y={85} stroke="var(--accent)" strokeDasharray="3 3" />
        <ReferenceLine y={65} stroke="var(--gold)" strokeDasharray="3 3" />
        <ReferenceLine y={40} stroke="var(--danger)" strokeDasharray="3 3" />
        <Area type="monotone" dataKey="c" stroke={color} strokeWidth={2.5} fill="url(#trustFill)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
