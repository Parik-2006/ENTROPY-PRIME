/**
 * ShadowEnvView — "Attacker View": the rendered honeypot environments.
 *
 * PRESENTATION BUILD — exactly three finished, credible environments, all
 * generated CLIENT-SIDE from a seed (always visual, no backend dependency, fully
 * isolated synthetic data):
 *
 *   presentation = 'banking'    → Banking Shadow Environment   (Credential Stuffing)
 *   presentation = 'terminal'   → Recon Sandbox Terminal       (Reconnaissance)
 *   presentation = 'bruteforce' → Argon2id + Tarpit            (Brute Force)
 */

import { useMemo, useState, useEffect, useRef } from 'react'

/* ── seeded synthetic-data generator ── */
function mulberry32(seed) { let a = seed >>> 0; return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296 } }
const hashSeed = (s) => { let h = 0x811c9dc5; for (const c of String(s)) { h ^= c.charCodeAt(0); h = Math.imul(h, 0x01000193) } return h >>> 0 }
const FIRST = ['James', 'Mary', 'Robert', 'Patricia', 'John', 'Jennifer', 'Michael', 'Linda', 'David', 'Susan', 'Aisha', 'Wei', 'Priya', 'Diego', 'Fatima', 'Omar', 'Sofia', 'Liam', 'Nadia', 'Yuki']
const LAST = ['Smith', 'Johnson', 'Williams', 'Brown', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Khan', 'Chen', 'Patel', 'Nguyen', 'Okafor', 'Rossi', 'Haddad', 'Novak', 'Kim', 'Lopez', 'Wilson']
const MERCH = ['Amazon', 'Whole Foods', 'Shell', 'Netflix', 'Uber', 'Starbucks', 'Apple Store', 'Target', 'Spotify', 'Delta', 'IKEA', 'Costco', 'Steam', 'DoorDash', 'CVS']
const BANKS = ['First National', 'Meridian Trust', 'Coastal Federal', 'Summit Bank', 'Atlas Financial']
function makeGen(token) {
  const rnd = mulberry32(hashSeed(token || 'demo'))
  const pick = (a) => a[Math.floor(rnd() * a.length)]
  const int = (lo, hi) => Math.floor(lo + rnd() * (hi - lo + 1))
  const money = (lo, hi) => Math.round(Math.exp(Math.log(lo) + rnd() * (Math.log(hi) - Math.log(lo))) * 100) / 100
  const name = () => `${pick(FIRST)} ${pick(LAST)}`
  const email = (n) => `${(n || name()).toLowerCase().replace(' ', '.')}${int(1, 99)}@${pick(['gmail.com', 'outlook.com', 'proton.me', 'icloud.com'])}`
  const acct = () => Array.from({ length: 12 }, () => int(0, 9)).join('')
  const date = (m = 180) => new Date(Date.now() - int(0, m) * 86400000).toISOString().slice(0, 10)
  return { rnd, pick, int, money, name, email, acct, date }
}
const usd = (n) => '$' + Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
// Indian rupee with lakh/crore grouping, e.g. ₹2,84,51,920 — used by the shadow
// CORPORATE bank to look dramatically unlike the real retail app.
const inr = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })

export default function ShadowEnvView({ token, presentation = 'banking' }) {
  const g = useMemo(() => makeGen(token), [token])
  if (presentation === 'terminal')   return <ReconTerminal g={g} />
  if (presentation === 'bruteforce') return <BruteForceSequence g={g} />
  return <BankingWorld g={g} />
}

/* ════════════════════════ 1 · BANKING SHADOW ENVIRONMENT ════════════════════════
 * Deliberately DISTINCT from the real retail app (Entropy Bank, blue/teal,
 * ₹ retail amounts, "Parikshith / Student"). The shadow world is a CORPORATE
 * treasury bank — dark + gold theme, a loud deception banner, ₹ corporate-scale
 * amounts, corporate transactions and a Platinum Enterprise persona — so faculty
 * instantly see "this is a different, fake banking world."                       */
const BANK_TABS = ['overview', 'accounts', 'transactions', 'beneficiaries', 'investments', 'loans', 'statements', 'profile']
const CORP_TXN = ['International Wire Transfer', 'Corporate Settlement', 'Treasury Movement', 'FX Hedge Settlement', 'Bond Coupon Payment', 'Payroll Disbursement', 'Inter-company Transfer', 'Letter of Credit', 'Custody Fee', 'Dividend Distribution']
const CORP_PAYEE = ['Helix Industries Ltd', 'Nimbus Trading FZE', 'Apex Capital Partners', 'Orion Logistics Pvt Ltd', 'Vanguard Holdings SA', 'Crestline Exports Ltd', 'Stellar Infra LLC']
const CORP_BANKS = ['HSBC Corporate', 'Citi Treasury', 'Standard Chartered', 'Deutsche Bank AG', 'JP Morgan Chase']

function BankingWorld({ g }) {
  const [tab, setTab] = useState('overview')
  const d = useMemo(() => {
    const accounts = [
      { id: g.acct(), type: 'Corporate Current A/C', bank: g.pick(CORP_BANKS), balance: g.money(8_00_000, 9_00_00_000) },
      { id: g.acct(), type: 'Treasury Reserve', bank: g.pick(CORP_BANKS), balance: g.money(50_00_000, 18_00_00_000) },
      { id: g.acct(), type: 'FX Settlement A/C', bank: g.pick(CORP_BANKS), balance: g.money(20_00_000, 6_00_00_000) },
      { id: g.acct(), type: 'Escrow Holdings', bank: g.pick(CORP_BANKS), balance: g.money(10_00_000, 4_00_00_000) },
    ]
    return {
      accounts, total: accounts.reduce((s, a) => s + a.balance, 0),
      txns: Array.from({ length: 14 }, () => { const a = g.money(50_000, 2_50_00_000), cr = g.rnd() > 0.55; return { id: i32(g), date: g.date(90), desc: g.pick(CORP_TXN), ref: 'REF' + g.int(10000000, 99999999), amount: cr ? a : -a } }),
      payees: Array.from({ length: 6 }, () => ({ id: i32(g), name: g.pick(CORP_PAYEE), bank: g.pick(CORP_BANKS), acct: g.acct(), country: g.pick(['UAE', 'Singapore', 'UK', 'Switzerland', 'USA']) })),
      invest: [
        { name: 'Sovereign Bond Portfolio', units: g.int(5000, 90000), value: g.money(1_00_00_000, 22_00_00_000), chg: (g.rnd() * 8 - 1) },
        { name: 'Corporate Bond Fund', units: g.int(2000, 50000), value: g.money(50_00_000, 9_00_00_000), chg: (g.rnd() * 12 - 3) },
        { name: 'Equity Treasury Holdings', units: g.int(1000, 30000), value: g.money(40_00_000, 14_00_00_000), chg: (g.rnd() * 28 - 9) },
        { name: 'Money Market Fund', units: g.int(10000, 200000), value: g.money(30_00_000, 7_00_00_000), chg: 6.4 },
      ],
      loans: [
        { type: 'Working Capital Facility', bal: g.money(50_00_000, 12_00_00_000), rate: (g.int(78, 110) / 10), term: 'Revolving' },
        { type: 'Term Loan', bal: g.money(1_00_00_000, 20_00_00_000), rate: (g.int(85, 120) / 10), term: '84 mo' },
        { type: 'Trade Finance Line', bal: g.money(20_00_000, 8_00_00_000), rate: (g.int(70, 95) / 10), term: '180 days' },
      ],
      statements: Array.from({ length: 8 }, (_, i) => ({ period: `2025-${String(12 - i).padStart(2, '0')}`, open: g.money(50_00_000, 5_00_00_000), close: g.money(50_00_000, 5_00_00_000) })),
    }
  }, [g])
  const investTotal = d.invest.reduce((s, x) => s + x.value, 0)

  return (
    <div style={sb.app}>
      {/* loud deception banner — instantly readable */}
      <div style={sb.banner}>
        <span style={sb.bIcon}>⚠</span>
        <span><b>DECEPTION ENVIRONMENT ACTIVE</b> · Attacker View · Synthetic Banking World — not the original system</span>
      </div>
      <header style={sb.bar}>
        <strong style={sb.brand}>❖ VAULTLINE CAPITAL <span style={sb.brandSub}>Corporate Treasury</span></strong>
        <span style={sb.secure}>● Enterprise session</span>
      </header>
      <div style={sb.shell}>
        <nav style={sb.nav}>
          {BANK_TABS.map(t => <button key={t} onClick={() => setTab(t)} style={{ ...sb.navItem, ...(tab === t ? sb.navActive : {}) }}>{cap(t)}</button>)}
          <div style={sb.foot}>Synthetic · Isolated · Monitored</div>
        </nav>
        <main style={sb.main}>
          {tab === 'overview' && <>
            <h2 style={sb.h2}>Corporate Treasury Overview</h2>
            <div style={sb.cards}><CStat t="Total holdings" v={inr(d.total)} accent /><CStat t="Investments" v={inr(investTotal)} /><CStat t="Credit utilised" v={inr(d.loans.reduce((s, l) => s + l.bal, 0))} /><CStat t="Accounts" v={d.accounts.length} /></div>
            <div style={sb.alert}>Outbound International Wire Transfer of {inr(g.money(50_00_000, 2_00_00_000))} pending authorisation.</div>
            <div style={sb.alert}>Quarterly treasury statement generated for board review.</div>
          </>}
          {tab === 'accounts' && <CTable head={['Account', 'Bank', 'Number', 'Balance']} rows={d.accounts.map(a => [a.type, a.bank, '•••• ' + a.id.slice(-4), inr(a.balance)])} />}
          {tab === 'transactions' && <CTable head={['Date', 'Description', 'Reference', 'Amount']} rows={d.txns.map(t => [t.date, t.desc, t.ref, <span style={{ color: t.amount < 0 ? '#fca5a5' : '#86efac' }}>{t.amount < 0 ? '-' : '+'}{inr(Math.abs(t.amount))}</span>])} />}
          {tab === 'beneficiaries' && <CTable head={['Beneficiary', 'Bank', 'Country', 'Account']} rows={d.payees.map(p => [p.name, p.bank, p.country, '•••• ' + p.acct.slice(-4)])} />}
          {tab === 'investments' && <>
            <div style={sb.summaryBar}>Portfolio value <strong style={{ color: '#e8c468' }}>{inr(investTotal)}</strong></div>
            <CTable head={['Holding', 'Units', 'Value', 'Return']} rows={d.invest.map(x => [x.name, x.units.toLocaleString('en-IN'), inr(x.value), <span style={{ color: x.chg < 0 ? '#fca5a5' : '#86efac' }}>{x.chg >= 0 ? '+' : ''}{x.chg.toFixed(1)}%</span>])} />
          </>}
          {tab === 'loans' && <CTable head={['Facility', 'Outstanding', 'Rate', 'Term']} rows={d.loans.map(l => [l.type, inr(l.bal), l.rate + '%', l.term])} />}
          {tab === 'statements' && <CTable head={['Period', 'Opening', 'Closing', '']} rows={d.statements.map(s => [s.period, inr(s.open), inr(s.close), <a style={sb.link} href="#" onClick={e => e.preventDefault()}>⬇ PDF</a>])} />}
          {tab === 'profile' && <div style={sb.kv}>{Object.entries({ Name: 'Corporate Banking User', Entity: g.pick(['Vaultline Holdings Ltd', 'Apex Global Pvt Ltd', 'Meridian Corp Group']), 'Corporate ID': 'CORP-' + g.int(100000, 999999), 'Relationship Manager': g.name(), Tier: 'Platinum Enterprise', 'KYC status': 'Verified · Enhanced' }).map(([k, v]) => <div key={k} style={sb.kvRow}><span style={sb.kvK}>{k}</span><span style={{ color: '#e8e2d0' }}>{v}</span></div>)}</div>}
        </main>
      </div>
    </div>
  )
}
function CStat({ t, v, accent }) { return <div style={{ ...sb.stat, ...(accent ? { borderColor: '#6b5a2e' } : {}) }}><div style={{ ...sb.statV, color: accent ? '#e8c468' : '#e8e2d0' }}>{v}</div><div style={sb.statT}>{t}</div></div> }
function CTable({ head, rows }) { return <table style={sb.table}><thead><tr>{head.map(h => <th key={h} style={sb.th}>{h}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} style={sb.td}>{c}</td>)}</tr>)}</tbody></table> }

/* ════════════════════════ 2 · RECON SANDBOX TERMINAL ════════════════════════ */
function ReconTerminal({ g }) {
  // command → output lines. Output is believable but entirely FAKE / canary.
  const script = useMemo(() => ([
    { cmd: 'whoami', out: ['root'], secret: false },
    { cmd: 'pwd', out: ['/var/www/banking-app'], secret: false },
    { cmd: 'ls -la', out: ['drwxr-xr-x  app/   config/   logs/', '-rw-r--r--  credentials.txt   .env   docker-compose.yml', '-rw-------  server.key   backup.sql'], secret: false },
    { cmd: 'cat credentials.txt', out: ['admin:admin123', 'dbuser:S3cur3P@ss!', 'backup_svc:b4ckup-2024'], secret: true },
    { cmd: 'cat .env', out: ['DATABASE_URL=postgres://admin:' + g.pick(['k3y', 'p@ss', 'r00t']) + '@db.internal:5432/prod', 'AWS_ACCESS_KEY_ID=AKIA' + tok(g, 16).toUpperCase(), 'AWS_SECRET_ACCESS_KEY=' + tok(g, 40), 'STRIPE_SECRET_KEY=sk_live_' + tok(g, 24)], secret: true, canary: true },
    { cmd: 'find / -name "*.key" 2>/dev/null', out: ['/var/www/banking-app/server.key', '/etc/ssl/private/api.key', '/root/.ssh/id_rsa'], secret: true },
    { cmd: 'curl -s http://localhost/admin', out: ['{ "panel": "admin", "users": 1284, "role": "superuser", "mfa": false }'], secret: false },
    { cmd: 'curl -s http://localhost/api/users', out: ['[{"id":1,"user":"' + g.email() + '","role":"admin"},', ' {"id":2,"user":"' + g.email() + '","role":"ops"}, … 1282 more]'], secret: true, canary: true },
  ]), [g])

  const [lines, setLines] = useState([])           // rendered history
  const [typed, setTyped] = useState('')           // current command being typed
  const [tele, setTele] = useState({ cmds: 0, secrets: 0, canary: 0, secs: 0 })
  const step = useRef(0); const ci = useRef(0); const phase = useRef('type')
  const t0 = useRef(Date.now())

  useEffect(() => {
    const clock = setInterval(() => setTele(t => ({ ...t, secs: Math.floor((Date.now() - t0.current) / 1000) })), 1000)
    const iv = setInterval(() => {
      const s = script[step.current]
      if (!s) { clearInterval(iv); return }
      if (phase.current === 'type') {
        if (ci.current <= s.cmd.length) { setTyped(s.cmd.slice(0, ci.current)); ci.current++ }
        else { phase.current = 'run' }
      } else if (phase.current === 'run') {
        setLines(L => [...L, { type: 'cmd', text: s.cmd }, ...s.out.map(o => ({ type: 'out', text: o, secret: s.secret }))])
        setTyped('')
        setTele(t => ({ ...t, cmds: t.cmds + 1, secrets: t.secrets + (s.secret ? 1 : 0), canary: t.canary + (s.canary ? 1 : 0) }))
        ci.current = 0; phase.current = 'type'; step.current++
      }
    }, 55)
    return () => { clearInterval(iv); clearInterval(clock) }
  }, [script])

  const done = step.current >= script.length
  return (
    <div style={tm.wrap}>
      <div style={tm.termCol}>
        <div style={tm.bar}><span style={tm.dot('#ff5f56')} /><span style={tm.dot('#ffbd2e')} /><span style={tm.dot('#27c93f')} /><span style={tm.barT}>root@banking-app: ~ — recon-sandbox (isolated)</span></div>
        <div style={tm.screen}>
          {lines.map((l, i) => (
            <div key={i} style={l.type === 'cmd' ? tm.cmd : { ...tm.out, color: l.secret ? '#ffd166' : '#9ad1a5' }}>
              {l.type === 'cmd' ? <><span style={tm.prompt}>root@app:~$ </span>{l.text}</> : l.text}
            </div>
          ))}
          {!done && <div style={tm.cmd}><span style={tm.prompt}>root@app:~$ </span>{typed}<span style={tm.cursor}>▋</span></div>}
          {done && <div style={{ ...tm.out, color: '#9ad1a5' }}><span style={tm.prompt}>root@app:~$ </span><span style={tm.cursor}>▋</span></div>}
        </div>
      </div>
      <aside style={tm.tele}>
        <div style={tm.teleHead}>SANDBOX TELEMETRY</div>
        <Tele k="Commands executed" v={tele.cmds} />
        <Tele k="Secrets accessed" v={tele.secrets} warn />
        <Tele k="Canary triggers" v={tele.canary} danger />
        <Tele k="Time spent" v={tele.secs + 's'} />
        <div style={tm.note}>The attacker is confined to an isolated sandbox. Every command and exfiltrated secret is fake and logged. The real infrastructure is never exposed.</div>
      </aside>
    </div>
  )
}

/* ════════════════════════ 3 · ARGON2id + TARPIT ════════════════════════ */
const ATTEMPT_RAMP = [1, 15, 90, 500, 2000, 10000]
const TARPIT_STEPS = ['Authenticating…', 'Checking credentials…', 'Loading user profile…', 'Verifying session…']
function BruteForceSequence({ g }) {
  const [attempts, setAttempts] = useState(0)
  const [ramp, setRamp] = useState(0)        // index into ATTEMPT_RAMP
  const [stage, setStage] = useState('ramp') // ramp → protect → exhaust → tarpit → retry
  const [cost, setCost] = useState({ mem: 12, cpu: 8 })
  const [tarpit, setTarpit] = useState(0)
  const [retry, setRetry] = useState(60)
  const [hashes, setHashes] = useState(0)

  useEffect(() => {
    if (stage !== 'ramp') return
    if (ramp >= ATTEMPT_RAMP.length) { setStage('protect'); return }
    const target = ATTEMPT_RAMP[ramp]
    const iv = setInterval(() => setAttempts(a => {
      const next = Math.min(target, a + Math.ceil((target - a) / 4) + 1)
      setHashes(h => h + (next - a))
      if (next >= target) { clearInterval(iv); setTimeout(() => setRamp(r => r + 1), 350) }
      return next
    }), 40)
    return () => clearInterval(iv)
  }, [ramp, stage])

  useEffect(() => {
    if (stage !== 'protect') return
    const iv = setInterval(() => setCost(c => {
      const mem = Math.min(256, c.mem + 24), cpu = Math.min(100, c.cpu + 11)
      if (mem >= 256 && cpu >= 100) { clearInterval(iv); setTimeout(() => setStage('exhaust'), 700) }
      return { mem, cpu }
    }), 220)
    return () => clearInterval(iv)
  }, [stage])

  useEffect(() => { if (stage === 'exhaust') { const t = setTimeout(() => setStage('tarpit'), 1800); return () => clearTimeout(t) } }, [stage])
  useEffect(() => {
    if (stage !== 'tarpit') return
    if (tarpit >= TARPIT_STEPS.length) { setStage('retry'); return }
    const t = setTimeout(() => setTarpit(s => s + 1), 1400)   // artificial delay per step
    return () => clearTimeout(t)
  }, [stage, tarpit])
  useEffect(() => {
    if (stage !== 'retry') return
    const iv = setInterval(() => setRetry(r => (r <= 1 ? 60 : r - 1)), 1000)
    return () => clearInterval(iv)
  }, [stage])

  const threat = attempts > 1000 ? 'CRITICAL' : attempts > 100 ? 'HIGH' : 'ELEVATED'
  const wasted = Math.round(hashes * 0.35)   // ~0.35s per Argon2id verification (illustrative)

  return (
    <div style={bf.wrap}>
      <div style={bf.main}>
        {/* Phase 1 — attempts ramp */}
        <div style={bf.panel}>
          <div style={bf.panelH}>Password Attempts</div>
          <div style={bf.bigNum}>{attempts.toLocaleString()}</div>
          <div style={bf.ramp}>{ATTEMPT_RAMP.map((n, i) => <span key={n} style={{ ...bf.rampPip, ...(i <= ramp ? bf.rampOn : {}) }}>{n.toLocaleString()}</span>)}</div>
        </div>

        {/* Phase 2 — Argon2id protection */}
        {['protect', 'exhaust', 'tarpit', 'retry'].includes(stage) && (
          <div style={bf.panel}>
            <div style={bf.panelH}>🛡 Protection Layer Activated — <span style={{ color: '#34d399' }}>Argon2id</span> <span style={bf.tag}>OWASP recommended</span></div>
            <div style={bf.note}>Argon2id is <b>memory-hard and computationally expensive</b>. Each guess must allocate large memory and burn CPU — so verification stays cheap for one real login but is ruinous at brute-force scale.</div>
            <Bar k="Memory cost / guess" v={cost.mem} max={256} unit=" MB" />
            <Bar k="CPU cost / guess" v={cost.cpu} max={100} unit="%" />
          </div>
        )}

        {/* Phase 3 — exhaustion */}
        {['exhaust', 'tarpit', 'retry'].includes(stage) && (
          <div style={bf.panel}>
            <div style={bf.panelH}>Attacker Resource Exhaustion</div>
            <div style={bf.kvRow}><span>Estimated cost to brute-force</span><b style={{ color: '#f87171' }}>Extremely high</b></div>
            <div style={bf.kvRow}><span>Brute-force efficiency</span><b style={{ color: '#f87171' }}>≈ 0 (near zero)</b></div>
            <div style={bf.kvRow}><span>Cracking feasibility</span><b style={{ color: '#34d399' }}>Not practical</b></div>
          </div>
        )}

        {/* Phase 4 — tarpit */}
        {['tarpit', 'retry'].includes(stage) && (
          <div style={bf.panel}>
            <div style={bf.panelH}>↳ Redirecting to Authentication Tarpit</div>
            <div style={bf.tarpit}>
              {TARPIT_STEPS.map((s, i) => (
                <div key={s} style={{ ...bf.tarpStep, opacity: i < tarpit ? 1 : i === tarpit && stage === 'tarpit' ? 1 : 0.3 }}>
                  {i < tarpit ? <span style={{ color: '#34d399' }}>✓</span> : i === tarpit && stage === 'tarpit' ? <span style={bf.spin} /> : <span style={{ color: '#475569' }}>○</span>} {s}
                </div>
              ))}
            </div>
            {stage === 'retry' && <div style={bf.retry}>🔒 Too many attempts. Please retry after <b>{retry}s</b>.</div>}
          </div>
        )}
      </div>

      <aside style={bf.tele}>
        <div style={bf.teleHead}>BRUTE-FORCE TELEMETRY</div>
        <Tele k="Attempts" v={attempts.toLocaleString()} />
        <Tele k="Hash verifications" v={hashes.toLocaleString()} />
        <Tele k="Time wasted (est.)" v={wasted.toLocaleString() + 's'} warn />
        <Tele k="Threat level" v={threat} danger />
        <div style={bf.note2}>The attacker burns time and compute on Argon2id while being held in a tarpit — the real account is never exposed and lockout is enforced.</div>
      </aside>
    </div>
  )
}

/* ── small shared bits ── */
const cap = (s) => s[0].toUpperCase() + s.slice(1)
const i32 = (g) => 'txn_' + Array.from({ length: 8 }, () => 'abcdef0123456789'[g.int(0, 15)]).join('')
const tok = (g, n) => Array.from({ length: n }, () => 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'[g.int(0, 61)]).join('')
function Stat({ t, v, accent }) { return <div style={{ ...bk.stat, ...(accent ? { borderColor: '#bcd4fb' } : {}) }}><div style={bk.statV(accent)}>{v}</div><div style={bk.statT}>{t}</div></div> }
function Table({ head, rows }) { return <table style={bk.table}><thead><tr>{head.map(h => <th key={h} style={bk.th}>{h}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} style={bk.td}>{c}</td>)}</tr>)}</tbody></table> }
function Tele({ k, v, warn, danger }) { return <div style={tm.teleRow}><span style={tm.teleK}>{k}</span><span style={{ ...tm.teleV, color: danger ? '#ff7875' : warn ? '#fbbf24' : '#cdd9e5' }}>{v}</span></div> }
function Bar({ k, v, max, unit }) { const w = Math.min(100, (v / max) * 100); return <div style={{ marginTop: 10 }}><div style={bf.barTop}><span style={bf.barK}>{k}</span><span style={bf.barV}>{v}{unit}</span></div><div style={bf.barTrack}><div style={{ ...bf.barFill, width: w + '%', background: w > 80 ? '#f87171' : '#fbbf24' }} /></div></div> }

/* ── styles ── */
const bk = {
  app: { background: '#f4f6f9', color: '#1f2a37', borderRadius: 12, overflow: 'hidden', border: '1px solid var(--border)', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  bar: { height: 52, background: '#0b3d91', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px', fontSize: 16 },
  secure: { fontSize: 11, color: '#bfe3c9' }, shell: { display: 'flex', minHeight: 380 },
  nav: { width: 168, background: '#fff', borderRight: '1px solid #e3e8ee', padding: 12, display: 'flex', flexDirection: 'column', gap: 3 },
  navItem: { textAlign: 'left', padding: '8px 12px', border: 'none', background: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13.5, color: '#3b4a5a' },
  navActive: { background: '#eaf1fd', color: '#0b5bd3', fontWeight: 600 }, fdic: { marginTop: 'auto', fontSize: 9, color: '#9aa7b4', padding: 8 },
  main: { flex: 1, padding: '22px 26px', overflow: 'auto' }, h2: { fontSize: 20, margin: '0 0 16px' },
  cards: { display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 },
  stat: { flex: '1 1 120px', border: '1px solid #e3e8ee', borderRadius: 10, padding: '14px 16px', background: '#fff' },
  statV: (a) => ({ fontSize: 21, fontWeight: 700, color: a ? '#0b5bd3' : '#0f172a' }), statT: { fontSize: 11, color: '#6b7785', marginTop: 4 },
  alert: { padding: '10px 12px', border: '1px solid #e3e8ee', borderRadius: 8, marginBottom: 8, fontSize: 13, background: '#fff' },
  summaryBar: { fontSize: 13, color: '#6b7785', marginBottom: 12 },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13, background: '#fff', border: '1px solid #e3e8ee', borderRadius: 10, overflow: 'hidden' },
  th: { textAlign: 'left', padding: '9px 12px', background: '#f7f9fc', color: '#6b7785', fontSize: 11, borderBottom: '1px solid #e3e8ee' },
  td: { padding: '9px 12px', borderBottom: '1px solid #eef2f6' }, link: { color: '#0b5bd3', textDecoration: 'none' },
  kv: { background: '#fff', border: '1px solid #e3e8ee', borderRadius: 10, overflow: 'hidden', maxWidth: 460 },
  kvRow: { display: 'flex', justifyContent: 'space-between', padding: '11px 16px', borderBottom: '1px solid #eef2f6', fontSize: 13 }, kvK: { color: '#6b7785' },
}
// Shadow CORPORATE bank theme — dark slate + gold, deliberately unlike the real app.
const sb = {
  app: { background: '#12100b', color: '#e8e2d0', borderRadius: 12, overflow: 'hidden', border: '1px solid #3a3220', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  banner: { display: 'flex', alignItems: 'center', gap: 10, padding: '9px 16px', background: 'linear-gradient(90deg,#7c1d1d,#b91c1c)', color: '#fff', fontSize: 12.5, letterSpacing: 0.2 },
  bIcon: { fontSize: 16 },
  bar: { height: 54, background: '#1a1710', borderBottom: '1px solid #3a3220', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px' },
  brand: { fontSize: 17, color: '#e8c468', letterSpacing: 0.5 }, brandSub: { fontSize: 10, color: '#9a8a5e', marginLeft: 8, letterSpacing: 1 },
  secure: { fontSize: 11, color: '#86efac' }, shell: { display: 'flex', minHeight: 380 },
  nav: { width: 184, background: '#17140d', borderRight: '1px solid #3a3220', padding: 12, display: 'flex', flexDirection: 'column', gap: 3 },
  navItem: { textAlign: 'left', padding: '8px 12px', border: 'none', background: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13.5, color: '#b3a888' },
  navActive: { background: '#2a2415', color: '#e8c468', fontWeight: 600 },
  foot: { marginTop: 'auto', fontSize: 9, color: '#7a6f4e', padding: 8, letterSpacing: 1 },
  main: { flex: 1, padding: '22px 26px', overflow: 'auto' }, h2: { fontSize: 20, margin: '0 0 16px', color: '#e8c468' },
  cards: { display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 },
  stat: { flex: '1 1 130px', border: '1px solid #3a3220', borderRadius: 10, padding: '14px 16px', background: '#1a1710' },
  statV: { fontSize: 20, fontWeight: 700 }, statT: { fontSize: 11, color: '#9a8a5e', marginTop: 4 },
  alert: { padding: '10px 12px', border: '1px solid #3a3220', borderRadius: 8, marginBottom: 8, fontSize: 13, background: '#1a1710', color: '#cfc6ab' },
  summaryBar: { fontSize: 13, color: '#9a8a5e', marginBottom: 12 },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13, background: '#1a1710', border: '1px solid #3a3220', borderRadius: 10, overflow: 'hidden' },
  th: { textAlign: 'left', padding: '9px 12px', background: '#221d12', color: '#9a8a5e', fontSize: 11, borderBottom: '1px solid #3a3220' },
  td: { padding: '9px 12px', borderBottom: '1px solid #2a2415', color: '#d8d0b8' }, link: { color: '#e8c468', textDecoration: 'none' },
  kv: { background: '#1a1710', border: '1px solid #3a3220', borderRadius: 10, overflow: 'hidden', maxWidth: 480 },
  kvRow: { display: 'flex', justifyContent: 'space-between', padding: '11px 16px', borderBottom: '1px solid #2a2415', fontSize: 13 }, kvK: { color: '#9a8a5e' },
}
const tm = {
  wrap: { display: 'flex', gap: 14, minHeight: 380 },
  termCol: { flex: 1, background: '#0b0f17', borderRadius: 12, overflow: 'hidden', border: '1px solid #1b2433' },
  bar: { display: 'flex', alignItems: 'center', gap: 7, padding: '9px 12px', background: '#161c28', borderBottom: '1px solid #1b2433' },
  dot: (c) => ({ width: 11, height: 11, borderRadius: '50%', background: c }), barT: { marginLeft: 8, fontSize: 11, color: '#6b7a90', fontFamily: 'monospace' },
  screen: { padding: 14, fontFamily: 'var(--mono, "Courier New", monospace)', fontSize: 12.5, lineHeight: 1.55, height: 340, overflow: 'auto' },
  cmd: { color: '#e2e8f0', whiteSpace: 'pre-wrap' }, out: { whiteSpace: 'pre-wrap' }, prompt: { color: '#38bdf8' }, cursor: { color: '#38bdf8' },
  tele: { width: 230, background: '#0d1117', border: '1px solid #1e293b', borderRadius: 12, padding: 14, display: 'flex', flexDirection: 'column', gap: 8 },
  teleHead: { fontSize: 10, letterSpacing: 1.5, color: '#5a6b7d', marginBottom: 4 },
  teleRow: { display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid #18222f' },
  teleK: { fontSize: 12, color: '#8a98a8' }, teleV: { fontSize: 14, fontWeight: 700, fontFamily: 'monospace' },
  note: { marginTop: 'auto', fontSize: 10.5, color: '#5f7186', lineHeight: 1.5 },
}
const bf = {
  wrap: { display: 'flex', gap: 14, minHeight: 380 },
  main: { flex: 1, display: 'flex', flexDirection: 'column', gap: 12 },
  panel: { background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 12, padding: '14px 18px' },
  panelH: { fontSize: 13, fontWeight: 700, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  bigNum: { fontSize: 40, fontWeight: 800, color: '#f87171', fontVariantNumeric: 'tabular-nums', lineHeight: 1 },
  ramp: { display: 'flex', gap: 6, marginTop: 12, flexWrap: 'wrap' },
  rampPip: { fontSize: 11, padding: '3px 9px', borderRadius: 20, border: '1px solid var(--border)', color: 'var(--text-3)', fontFamily: 'monospace' },
  rampOn: { background: 'rgba(248,113,113,.14)', borderColor: 'rgba(248,113,113,.5)', color: '#f87171' },
  tag: { fontSize: 10, background: 'rgba(52,211,153,.14)', color: '#34d399', padding: '2px 8px', borderRadius: 6 },
  note: { fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.55, marginBottom: 6 },
  kvRow: { display: 'flex', justifyContent: 'space-between', padding: '7px 0', fontSize: 13, borderBottom: '1px solid var(--border)' },
  barTop: { display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }, barK: { color: 'var(--text-3)' }, barV: { fontFamily: 'monospace', fontWeight: 700 },
  barTrack: { height: 9, background: 'var(--surface-3)', borderRadius: 99, overflow: 'hidden' }, barFill: { height: '100%', borderRadius: 99, transition: 'width .25s' },
  tarpit: { display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4, fontFamily: 'monospace', fontSize: 13 },
  tarpStep: { display: 'flex', alignItems: 'center', gap: 10, transition: 'opacity .3s' },
  spin: { width: 13, height: 13, borderRadius: '50%', border: '2px solid var(--surface-3)', borderTopColor: 'var(--accent)', display: 'inline-block', animation: 'spin .8s linear infinite' },
  retry: { marginTop: 12, padding: '10px 12px', background: 'rgba(251,191,36,.1)', border: '1px solid rgba(251,191,36,.3)', borderRadius: 8, fontSize: 13, color: '#d99a00' },
  tele: { width: 230, background: '#0d1117', border: '1px solid #1e293b', borderRadius: 12, padding: 14, display: 'flex', flexDirection: 'column', gap: 8 },
  teleHead: { fontSize: 10, letterSpacing: 1.5, color: '#5a6b7d', marginBottom: 4 },
  note2: { marginTop: 'auto', fontSize: 10.5, color: '#5f7186', lineHeight: 1.5 },
}
