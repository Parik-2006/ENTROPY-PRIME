import { useState, useEffect, useRef, useCallback } from 'react'

// ── World city coordinates (normalized to 800x400 SVG viewBox) ──────────────
const CITIES = [
  { id: 'nyc',  name: 'New York',    x: 168, y: 148, region: 'NA' },
  { id: 'lon',  name: 'London',      x: 368, y: 112, region: 'EU' },
  { id: 'par',  name: 'Paris',       x: 378, y: 120, region: 'EU' },
  { id: 'ber',  name: 'Berlin',      x: 398, y: 106, region: 'EU' },
  { id: 'msc',  name: 'Moscow',      x: 452, y: 94,  region: 'EU' },
  { id: 'bej',  name: 'Beijing',     x: 598, y: 136, region: 'AS' },
  { id: 'tok',  name: 'Tokyo',       x: 658, y: 148, region: 'AS' },
  { id: 'mum',  name: 'Mumbai',      x: 538, y: 196, region: 'AS' },
  { id: 'syd',  name: 'Sydney',      x: 668, y: 302, region: 'OC' },
  { id: 'sao',  name: 'São Paulo',   x: 228, y: 282, region: 'SA' },
  { id: 'dub',  name: 'Dubai',       x: 498, y: 186, region: 'ME' },
  { id: 'sin',  name: 'Singapore',   x: 612, y: 236, region: 'AS' },
  { id: 'lag',  name: 'Lagos',       x: 368, y: 232, region: 'AF' },
  { id: 'jnb',  name: 'Johannesburg',x: 418, y: 310, region: 'AF' },
  { id: 'chi',  name: 'Chicago',     x: 156, y: 140, region: 'NA' },
  { id: 'lax',  name: 'Los Angeles', x: 110, y: 162, region: 'NA' },
  { id: 'fra',  name: 'Frankfurt',   x: 395, y: 113, region: 'EU' },
  { id: 'ams',  name: 'Amsterdam',   x: 376, y: 107, region: 'EU' },
  { id: 'tor',  name: 'Toronto',     x: 174, y: 134, region: 'NA' },
  { id: 'mex',  name: 'Mexico City', x: 138, y: 194, region: 'NA' },
]

// Simplified continent paths
const CONTINENTS = [
  // North America
  { d: 'M 92,72 L 118,58 L 160,52 L 200,58 L 218,80 L 232,118 L 224,172 L 202,208 L 182,218 L 158,210 L 130,196 L 100,166 L 82,140 L 80,104 Z', fill: 'rgba(0,229,255,0.04)', stroke: 'rgba(0,229,255,0.12)' },
  // South America
  { d: 'M 168,218 L 210,210 L 238,226 L 258,270 L 248,330 L 226,346 L 198,340 L 174,308 L 160,268 Z', fill: 'rgba(0,229,255,0.04)', stroke: 'rgba(0,229,255,0.12)' },
  // Europe
  { d: 'M 336,64 L 388,58 L 428,68 L 440,90 L 458,96 L 466,116 L 440,128 L 412,134 L 374,142 L 354,130 L 342,112 L 330,90 Z', fill: 'rgba(0,229,255,0.04)', stroke: 'rgba(0,229,255,0.12)' },
  // Africa
  { d: 'M 344,148 L 440,142 L 456,172 L 460,230 L 446,298 L 422,328 L 400,334 L 372,326 L 348,290 L 336,238 L 336,192 Z', fill: 'rgba(0,229,255,0.04)', stroke: 'rgba(0,229,255,0.12)' },
  // Asia
  { d: 'M 440,64 L 530,52 L 620,56 L 700,72 L 712,118 L 698,156 L 654,174 L 610,178 L 568,198 L 530,198 L 490,174 L 460,164 L 438,134 L 428,102 Z', fill: 'rgba(0,229,255,0.04)', stroke: 'rgba(0,229,255,0.12)' },
  // Australia
  { d: 'M 620,258 L 700,252 L 722,282 L 718,316 L 690,332 L 648,328 L 620,308 L 608,282 Z', fill: 'rgba(0,229,255,0.04)', stroke: 'rgba(0,229,255,0.12)' },
]

// Generate a cubic bezier arc between two points (always bowing upward)
function arcPath(x1, y1, x2, y2) {
  const mx = (x1 + x2) / 2
  const my = (y1 + y2) / 2
  const dx = x2 - x1
  const dy = y2 - y1
  const dist = Math.sqrt(dx * dx + dy * dy)
  const bow  = -dist * 0.35
  const cpx  = mx - (dy / dist) * bow
  const cpy  = my + (dx / dist) * bow
  return `M ${x1},${y1} Q ${cpx},${cpy} ${x2},${y2}`
}

// ── Threat event generator ─────────────────────────────────────────────────
let _eid = 0
function genThreat() {
  const src = CITIES[Math.floor(Math.random() * CITIES.length)]
  let dst
  do { dst = CITIES[Math.floor(Math.random() * CITIES.length)] } while (dst.id === src.id)
  const types  = ['BRUTE_FORCE', 'CREDENTIAL_STUFFING', 'BOT_WAVE', 'SCANNER', 'REPLAY_ATTACK', 'ENUM_ATTACK']
  const sevs   = ['critical', 'high', 'medium', 'low']
  const sevW   = [0.08, 0.22, 0.38, 0.32]
  let r = Math.random(), sev = 'low'
  let cum = 0; for (let i = 0; i < sevW.length; i++) { cum += sevW[i]; if (r < cum) { sev = sevs[i]; break } }
  return {
    id:    _eid++,
    src,
    dst,
    type:  types[Math.floor(Math.random() * types.length)],
    sev,
    ts:    Date.now(),
    path:  arcPath(src.x, src.y, dst.x, dst.y),
    alive: 3500 + Math.random() * 2000,
    born:  performance.now(),
  }
}

const SEV_COLOR = { critical: '#ff3b5c', high: '#ffb800', medium: '#00e5ff', low: '#00ffa3' }

// ── Component ──────────────────────────────────────────────────────────────
export default function ThreatMap({ height = 340, maxArcs = 12 }) {
  const [threats, setThreats]   = useState([])
  const [pings,   setPings]     = useState([])   // expanding circles
  const [stats,   setStats]     = useState({ total: 0, critical: 0, countries: new Set() })
  const rafRef = useRef(null)
  const lastSpawn = useRef(0)

  // Spawn + prune threats
  useEffect(() => {
    const tick = (now) => {
      const spawnInterval = 1200 + Math.random() * 800
      setThreats(prev => {
        const alive = prev.filter(t => now - t.born < t.alive)
        if (now - lastSpawn.current > spawnInterval && alive.length < maxArcs) {
          lastSpawn.current = now
          const t = genThreat()
          // Ping at source
          setPings(p => [...p.slice(-20), { id: t.id, x: t.src.x, y: t.src.y, sev: t.sev, born: now }])
          setStats(s => ({
            total: s.total + 1,
            critical: t.sev === 'critical' ? s.critical + 1 : s.critical,
            countries: new Set([...s.countries, t.src.region, t.dst.region]),
          }))
          return [...alive, t]
        }
        return alive
      })
      setPings(p => p.filter(pk => now - pk.born < 2000))
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [maxArcs])

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      {/* Stat bar above map */}
      <div style={{ display: 'flex', gap: 24, marginBottom: 10, paddingLeft: 4 }}>
        {[
          { label: 'ATTACKS DETECTED', val: stats.total, color: 'var(--danger)' },
          { label: 'CRITICAL',         val: stats.critical, color: '#ff3b5c' },
          { label: 'ACTIVE ARCS',      val: threats.length, color: 'var(--warn)' },
          { label: 'REGIONS HIT',      val: stats.countries.size, color: 'var(--accent)' },
        ].map(s => (
          <div key={s.label} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 18, fontWeight: 700, color: s.color }}>
              {s.val}
            </span>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 8, color: 'var(--text3)', letterSpacing: '1.5px' }}>
              {s.label}
            </span>
          </div>
        ))}
        {/* Legend */}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, alignItems: 'center' }}>
          {Object.entries(SEV_COLOR).map(([sev, col]) => (
            <span key={sev} style={{ display: 'flex', alignItems: 'center', gap: 5,
              fontFamily: 'var(--mono)', fontSize: 8, color: 'var(--text3)', letterSpacing: '1px' }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: col, display: 'inline-block' }} />
              {sev.toUpperCase()}
            </span>
          ))}
        </div>
      </div>

      {/* SVG map */}
      <svg
        viewBox="0 0 800 400"
        style={{ width: '100%', height, display: 'block', background: 'var(--bg)' }}
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <radialGradient id="tglow-crit" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ff3b5c" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#ff3b5c" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="tglow-high" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ffb800" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#ffb800" stopOpacity="0" />
          </radialGradient>
          <filter id="tglow">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="tglow-strong">
            <feGaussianBlur stdDeviation="3.5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Latitude grid lines */}
        {[60, 120, 180, 240, 300, 360].map(y => (
          <line key={y} x1={0} y1={y} x2={800} y2={y}
            stroke="rgba(0,229,255,0.04)" strokeWidth={0.5} />
        ))}
        {[80, 160, 240, 320, 400, 480, 560, 640, 720].map(x => (
          <line key={x} x1={x} y1={0} x2={x} y2={400}
            stroke="rgba(0,229,255,0.04)" strokeWidth={0.5} />
        ))}

        {/* Continents */}
        {CONTINENTS.map((c, i) => (
          <path key={i} d={c.d} fill={c.fill} stroke={c.stroke} strokeWidth={0.8} />
        ))}

        {/* Expanding ping rings at attack sources */}
        {pings.map(pk => {
          const col = SEV_COLOR[pk.sev]
          return (
            <g key={pk.id}>
              <circle cx={pk.x} cy={pk.y} r={0} fill="none" stroke={col} strokeWidth={1.5} opacity={0.9}>
                <animate attributeName="r" from={2} to={22} dur="1.8s" fill="freeze" />
                <animate attributeName="opacity" from={0.9} to={0} dur="1.8s" fill="freeze" />
              </circle>
              <circle cx={pk.x} cy={pk.y} r={0} fill="none" stroke={col} strokeWidth={0.8} opacity={0.5}>
                <animate attributeName="r" from={2} to={36} dur="1.8s" begin="0.3s" fill="freeze" />
                <animate attributeName="opacity" from={0.5} to={0} dur="1.8s" begin="0.3s" fill="freeze" />
              </circle>
            </g>
          )
        })}

        {/* Attack arcs */}
        {threats.map(t => {
          const col = SEV_COLOR[t.sev]
          const age = performance.now() - t.born
          const progress = Math.min(age / (t.alive * 0.7), 1)
          const opacity = progress < 0.8 ? 0.7 : 0.7 * (1 - (progress - 0.8) / 0.2)
          return (
            <g key={t.id} style={{ opacity }}>
              {/* Arc glow */}
              <path d={t.path} fill="none" stroke={col} strokeWidth={3} opacity={0.15}
                filter="url(#tglow)" />
              {/* Arc line */}
              <path d={t.path} fill="none" stroke={col} strokeWidth={1}
                strokeDasharray="6 4" opacity={0.6}>
                <animate attributeName="stroke-dashoffset" from="0" to="-40"
                  dur="1.2s" repeatCount="indefinite" />
              </path>
              {/* Traveling dot */}
              <circle r={t.sev === 'critical' ? 3.5 : 2.5} fill={col} filter="url(#tglow-strong)">
                <animateMotion path={t.path} dur={`${t.alive / 1000}s`} fill="freeze" />
              </circle>
            </g>
          )
        })}

        {/* City dots */}
        {CITIES.map(city => {
          const isTarget = threats.some(t => t.dst.id === city.id)
          const isSrc    = threats.some(t => t.src.id === city.id)
          const sev      = threats.find(t => t.src.id === city.id || t.dst.id === city.id)?.sev
          const col      = sev ? SEV_COLOR[sev] : 'rgba(0,229,255,0.5)'
          return (
            <g key={city.id}>
              {(isTarget || isSrc) && (
                <circle cx={city.x} cy={city.y} r={8} fill={col} opacity={0.08} />
              )}
              <circle cx={city.x} cy={city.y} r={isTarget ? 3 : 2}
                fill={col}
                filter={isTarget ? 'url(#tglow)' : undefined}
              />
              <circle cx={city.x} cy={city.y} r={1} fill="rgba(255,255,255,0.9)" />
            </g>
          )
        })}

        {/* "Equator" label */}
        <text x={6} y={202} fill="rgba(0,229,255,0.2)"
          style={{ fontFamily: 'monospace', fontSize: 7, letterSpacing: 1 }}>
          EQUATOR
        </text>
      </svg>

      {/* Live attack feed — small ticker */}
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 3, maxHeight: 76, overflow: 'hidden' }}>
        {threats.slice(-4).reverse().map(t => (
          <div key={t.id} style={{
            display: 'flex', gap: 10, alignItems: 'center',
            fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text3)',
            padding: '3px 8px',
            background: 'rgba(0,229,255,0.03)',
            borderLeft: `2px solid ${SEV_COLOR[t.sev]}`,
            animation: 'fadeIn .3s ease',
          }}>
            <span style={{ color: SEV_COLOR[t.sev], width: 52 }}>{t.sev.toUpperCase()}</span>
            <span style={{ color: 'var(--text2)' }}>{t.type}</span>
            <span>·</span>
            <span>{t.src.name}</span>
            <span style={{ color: 'var(--accent)' }}>→</span>
            <span>{t.dst.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}