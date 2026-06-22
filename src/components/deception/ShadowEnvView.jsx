/**
 * ShadowEnvView — "Attacker View": the actual rendered honeypot environments.
 *
 * DEMO-STABLE BUILD: each environment is generated CLIENT-SIDE from a seed
 * derived from the shadow session token, so the attacker view is always rich
 * and visual (it never depends on a live backend response). Everything here is
 * synthetic and isolated — no real data is touched.
 *
 *   presentation = 'banking'    → Banking Shadow World      (Credential Stuffing)
 *   presentation = 'admin'      → Shadow Admin World        (Reconnaissance)
 *   presentation = 'tarpit'     → Tarpit Environment        (Brute Force)
 *   presentation = 'scraper'    → Synthetic Dataset World   (Data Scraper)
 *   presentation = 'restricted' → Restricted Session Sandbox(Session Hijacking)
 */

import { useMemo, useState, useEffect, useRef } from 'react'

// ── Seeded synthetic-data generator ──────────────────────────────────────────
function mulberry32(seed) {
  let a = seed >>> 0
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const hashSeed = (s) => { let h = 0x811c9dc5; for (const c of String(s)) { h ^= c.charCodeAt(0); h = Math.imul(h, 0x01000193) } return h >>> 0 }

const FIRST = ['James', 'Mary', 'Robert', 'Patricia', 'John', 'Jennifer', 'Michael', 'Linda', 'David', 'Susan', 'Aisha', 'Wei', 'Priya', 'Diego', 'Fatima', 'Omar', 'Sofia', 'Liam', 'Nadia', 'Yuki']
const LAST = ['Smith', 'Johnson', 'Williams', 'Brown', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Khan', 'Chen', 'Patel', 'Nguyen', 'Okafor', 'Rossi', 'Haddad', 'Novak', 'Kim', 'Lopez', 'Wilson']
const MERCH = ['Amazon', 'Whole Foods', 'Shell', 'Netflix', 'Uber', 'Starbucks', 'Apple Store', 'Target', 'Spotify', 'Delta', 'IKEA', 'Costco', 'Steam', 'DoorDash', 'CVS Pharmacy']
const BANKS = ['First National', 'Meridian Trust', 'Coastal Federal', 'Summit Bank', 'Atlas Financial']
const ROLES = ['admin', 'manager', 'analyst', 'support', 'auditor', 'viewer']
const ACTIONS = ['login.success', 'login.failed', 'password.reset', 'role.changed', 'config.updated', 'export.csv', 'api_key.rotated', 'session.revoked']

function makeGen(token) {
  const rnd = mulberry32(hashSeed(token || 'demo'))
  const pick = (a) => a[Math.floor(rnd() * a.length)]
  const int = (lo, hi) => Math.floor(lo + rnd() * (hi - lo + 1))
  const money = (lo, hi) => Math.round((Math.exp(Math.log(lo) + rnd() * (Math.log(hi) - Math.log(lo)))) * 100) / 100
  const name = () => `${pick(FIRST)} ${pick(LAST)}`
  const email = (n) => `${(n || name()).toLowerCase().replace(' ', '.')}${int(1, 99)}@${pick(['gmail.com', 'outlook.com', 'proton.me', 'icloud.com'])}`
  const acct = () => Array.from({ length: 12 }, () => int(0, 9)).join('')
  const ip = () => Array.from({ length: 4 }, () => int(1, 254)).join('.')
  const date = (maxDaysAgo = 180) => { const d = new Date(Date.now() - int(0, maxDaysAgo) * 86400000 - int(0, 86400000)); return d.toISOString().slice(0, 16).replace('T', ' ') }
  const tok = (pfx, n = 24) => pfx + Array.from({ length: n }, () => 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'[int(0, 61)]).join('')
  return { rnd, pick, int, money, name, email, acct, ip, date, tok }
}

const usd = (n) => '$' + Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// ── Entry: pick the environment by presentation ──────────────────────────────
export default function ShadowEnvView({ token, presentation = 'banking' }) {
  const g = useMemo(() => makeGen(token), [token])
  switch (presentation) {
    case 'admin':      return <AdminWorld g={g} />
    case 'tarpit':     return <TarpitWorld g={g} />
    case 'scraper':    return <DatasetWorld g={g} />
    case 'restricted': return <RestrictedWorld g={g} />
    default:           return <BankingWorld g={g} />
  }
}

/* ════════════════════════ 1 · BANKING SHADOW WORLD ════════════════════════ */
function BankingWorld({ g }) {
  const [tab, setTab] = useState('overview')
  const data = useMemo(() => {
    const accounts = Array.from({ length: g.int(2, 4) }, (_, i) => ({
      id: g.acct(), type: ['Checking', 'Savings', 'Credit Card', 'Brokerage'][i % 4],
      bank: g.pick(BANKS), balance: g.money(120, 240000),
    }))
    return {
      name: g.name(), accounts,
      total: accounts.reduce((s, a) => s + a.balance, 0),
      txns: Array.from({ length: 14 }, () => { const amt = g.money(2, 6000); const credit = g.rnd() > 0.7; return { id: g.tok('txn_', 10), date: g.date(120), merchant: g.pick(MERCH), cat: g.pick(['Groceries', 'Travel', 'Dining', 'Utilities', 'Income', 'Transfer']), amount: credit ? amt : -amt } }),
      payees: Array.from({ length: g.int(3, 6) }, () => { const n = g.name(); return { id: g.tok('ben_', 8), nick: g.pick(['Mom', 'Rent', 'Landlord', 'Savings', n.split(' ')[0]]), name: n, bank: g.pick(BANKS), acct: g.acct() } }),
      statements: Array.from({ length: 8 }, (_, i) => ({ period: `2025-${String(12 - i).padStart(2, '0')}`, open: g.money(100, 40000), close: g.money(100, 40000) })),
    }
  }, [g])

  return (
    <div style={bk.app}>
      <header style={bk.bar}><strong>◆ Meridian Trust</strong><span style={bk.secure}>● Secure session</span></header>
      <div style={bk.shell}>
        <nav style={bk.nav}>
          {['overview', 'accounts', 'transactions', 'payees', 'statements'].map((t) => (
            <button key={t} onClick={() => setTab(t)} style={{ ...bk.navItem, ...(tab === t ? bk.navActive : {}) }}>{t[0].toUpperCase() + t.slice(1)}</button>
          ))}
          <div style={bk.fdic}>FDIC insured · Member FDIC</div>
        </nav>
        <main style={bk.main}>
          {tab === 'overview' && <>
            <h2 style={bk.h2}>Welcome back, {data.name.split(' ')[0]}</h2>
            <div style={bk.cards}>
              <Stat t="Total balance" v={usd(data.total)} accent /><Stat t="Accounts" v={data.accounts.length} /><Stat t="Pending" v={g.int(0, 4)} />
            </div>
            <div style={bk.alert}>Your monthly statement is ready to view.</div>
            <div style={bk.alert}>Payment to {g.pick(MERCH)} scheduled for next week.</div>
          </>}
          {tab === 'accounts' && <Table head={['Type', 'Bank', 'Number', 'Balance']} rows={data.accounts.map(a => [a.type, a.bank, '•••• ' + a.id.slice(-4), usd(a.balance)])} />}
          {tab === 'transactions' && <Table head={['Date', 'Description', 'Category', 'Amount']} rows={data.txns.map(t => [t.date, t.merchant, t.cat, <span style={{ color: t.amount < 0 ? '#b4232a' : '#137333' }}>{t.amount < 0 ? '-' : '+'}{usd(Math.abs(t.amount))}</span>])} />}
          {tab === 'payees' && <Table head={['Nickname', 'Name', 'Bank', 'Account']} rows={data.payees.map(p => [p.nick, p.name, p.bank, '•••• ' + p.acct.slice(-4)])} />}
          {tab === 'statements' && <Table head={['Period', 'Opening', 'Closing', '']} rows={data.statements.map(s => [s.period, usd(s.open), usd(s.close), <a style={bk.link} href="#" onClick={e => e.preventDefault()}>⬇ PDF</a>])} />}
        </main>
      </div>
    </div>
  )
}

/* ════════════════════════ 2 · SHADOW ADMIN WORLD ════════════════════════ */
function AdminWorld({ g }) {
  const [tab, setTab] = useState('dashboard')
  const data = useMemo(() => ({
    users: Array.from({ length: 12 }, () => { const n = g.name(); return { id: g.tok('usr_', 8), name: n, email: g.email(n), role: g.pick(ROLES), status: g.pick(['active', 'active', 'active', 'suspended']), last: g.date(40), mfa: g.rnd() > 0.4 } }),
    logs: Array.from({ length: 14 }, () => ({ ts: g.date(7), actor: g.email(), action: g.pick(ACTIONS), ip: g.ip(), result: g.pick(['ok', 'ok', 'ok', 'denied']) })),
    secrets: [
      { name: 'AWS_ACCESS_KEY_ID', value: 'AKIA' + g.tok('', 16).toUpperCase() },
      { name: 'AWS_SECRET_ACCESS_KEY', value: g.tok('', 40) },
      { name: 'STRIPE_SECRET_KEY', value: 'sk_live_' + g.tok('', 24) },
      { name: 'DATABASE_URL', value: `postgres://admin:${g.tok('', 12)}@db.internal:5432/prod` },
      { name: 'JWT_SIGNING_KEY', value: g.tok('', 48) },
    ],
    metrics: { cpu: g.int(18, 86), mem: g.int(30, 78), disk: g.int(40, 90), uptime: g.int(30, 700), reqs: g.int(800, 9000) },
    server: { host: g.pick(['prod-cluster-1', 'prod-eu-west', 'primary-node-3']), os: 'Ubuntu 22.04 LTS', kernel: '5.15.0-91-generic', region: g.pick(['us-east-1', 'eu-west-1', 'ap-south-1']), version: `${g.int(2, 5)}.${g.int(0, 9)}.${g.int(0, 30)}` },
  }), [g])
  const [shown, setShown] = useState({})

  return (
    <div style={ad.app}>
      <aside style={ad.side}>
        <div style={ad.brand}>▣ Console</div>
        {['dashboard', 'users', 'server', 'secrets', 'logs'].map((t) => (
          <button key={t} onClick={() => setTab(t)} style={{ ...ad.navItem, ...(tab === t ? ad.navActive : {}) }}>{t === 'secrets' ? 'API Keys' : t === 'server' ? 'Server' : t[0].toUpperCase() + t.slice(1)}</button>
        ))}
        <div style={ad.foot}>v{data.server.version} · prod</div>
      </aside>
      <main style={ad.main}>
        {tab === 'dashboard' && <>
          <h2 style={ad.h2}>System Dashboard</h2>
          <div style={ad.statRow}>
            <DStat t="Active users" v={Number(data.metrics.reqs).toLocaleString()} /><DStat t="CPU" v={data.metrics.cpu + '%'} /><DStat t="Memory" v={data.metrics.mem + '%'} /><DStat t="Uptime" v={data.metrics.uptime + 'd'} />
          </div>
          <div style={ad.bars}>
            {[['CPU', data.metrics.cpu], ['Memory', data.metrics.mem], ['Disk', data.metrics.disk]].map(([k, v]) => (
              <div key={k} style={ad.barRow}><span style={ad.barK}>{k}</span><div style={ad.track}><div style={{ ...ad.fill, width: v + '%', background: v > 80 ? '#f87171' : '#38bdf8' }} /></div><span style={ad.barV}>{v}%</span></div>
            ))}
          </div>
        </>}
        {tab === 'users' && <ATable head={['Name', 'Email', 'Role', 'Status', 'MFA']} rows={data.users.map(u => [u.name, u.email, <span style={ad.roleTag}>{u.role}</span>, <span style={{ color: u.status === 'active' ? '#34d399' : '#fbbf24' }}>{u.status}</span>, u.mfa ? 'on' : 'off'])} />}
        {tab === 'server' && <div style={ad.kv}>{Object.entries({ Hostname: data.server.host, OS: data.server.os, Kernel: data.server.kernel, Region: data.server.region, Version: data.server.version, 'Requests/min': data.metrics.reqs }).map(([k, v]) => <div key={k} style={ad.kvRow}><span style={ad.kvK}>{k}</span><code style={ad.code}>{String(v)}</code></div>)}</div>}
        {tab === 'secrets' && <>
          <p style={ad.warn}>⚠ Production secrets — rotate regularly.</p>
          <ATable head={['Name', 'Value', '']} rows={data.secrets.map(s => [<code style={ad.code}>{s.name}</code>, <code style={{ ...ad.code, color: '#e2e8f0' }}>{shown[s.name] ? s.value : '•'.repeat(28)}</code>, <button style={ad.smallBtn} onClick={() => setShown(p => ({ ...p, [s.name]: !p[s.name] }))}>{shown[s.name] ? 'Hide' : 'Reveal'}</button>])} />
        </>}
        {tab === 'logs' && <ATable head={['Time', 'Actor', 'Action', 'IP', 'Result']} rows={data.logs.map(l => [l.ts, l.actor, <code style={ad.code}>{l.action}</code>, l.ip, <span style={{ color: l.result === 'ok' ? '#34d399' : '#f87171' }}>{l.result}</span>])} />}
      </main>
    </div>
  )
}

/* ════════════════════════ 3 · TARPIT ENVIRONMENT ════════════════════════ */
function TarpitWorld({ g }) {
  const [phase, setPhase] = useState('idle')   // idle | auth | error | locked
  const [attempt, setAttempt] = useState(0)
  const [lockLeft, setLockLeft] = useState(0)
  const timer = useRef(null)

  const submit = () => {
    if (phase === 'auth' || phase === 'locked') return
    setPhase('auth')
    // Deliberate tarpit delay — responses get slower each attempt.
    const delay = 2200 + attempt * 1500
    timer.current = setTimeout(() => {
      const n = attempt + 1
      setAttempt(n)
      if (n >= 4) { setPhase('locked'); setLockLeft(30) }
      else setPhase('error')
    }, delay)
  }
  useEffect(() => () => clearTimeout(timer.current), [])
  useEffect(() => {
    if (phase !== 'locked') return
    const iv = setInterval(() => setLockLeft((s) => (s <= 1 ? (clearInterval(iv), setPhase('error'), 0) : s - 1)), 1000)
    return () => clearInterval(iv)
  }, [phase])

  return (
    <div style={tp.app}>
      <div style={tp.card}>
        <div style={tp.logo}>🔐 SecureBank</div>
        <div style={tp.sub}>Sign in to your account</div>
        <input style={tp.input} placeholder="Username" defaultValue="admin" />
        <input style={tp.input} type="password" placeholder="Password" defaultValue="••••••••" />
        <button style={{ ...tp.btn, opacity: phase === 'auth' || phase === 'locked' ? 0.6 : 1 }} disabled={phase === 'auth' || phase === 'locked'} onClick={submit}>
          {phase === 'auth' ? 'Authenticating…' : phase === 'locked' ? `Locked (${lockLeft}s)` : 'Sign In'}
        </button>
        {phase === 'auth' && <div style={tp.spin}><span style={tp.spinner} /> Verifying credentials… please wait</div>}
        {phase === 'error' && <div style={tp.err}>Invalid username or password. Attempt {attempt} of 4.</div>}
        {phase === 'locked' && <div style={tp.lock}>🚫 Account temporarily locked due to repeated failed attempts. Try again in {lockLeft}s.</div>}
        <div style={tp.foot}>Protected by SecureBank · Suspicious activity is monitored.</div>
      </div>
    </div>
  )
}

/* ════════════════════════ 4 · SYNTHETIC DATASET WORLD ════════════════════════ */
function DatasetWorld({ g }) {
  const [tab, setTab] = useState('customers')
  const rows = useMemo(() => ({
    customers: Array.from({ length: 40 }, (_, i) => { const n = g.name(); return [String(1000 + i), n, g.email(n), g.pick(['US', 'UK', 'IN', 'DE', 'BR', 'JP']), g.pick(['Active', 'Active', 'Dormant', 'Closed'])] }),
    accounts: Array.from({ length: 40 }, (_, i) => [g.acct(), g.pick(['Checking', 'Savings', 'Credit', 'Loan']), g.pick(BANKS), usd(g.money(50, 320000)), g.date(900).slice(0, 10)]),
    transactions: Array.from({ length: 40 }, () => { const amt = g.money(1, 9000); return [g.tok('tx_', 8), g.date(365), g.pick(MERCH), usd(amt), g.pick(['posted', 'posted', 'pending'])] }),
  }), [g])
  const head = { customers: ['ID', 'Name', 'Email', 'Country', 'Status'], accounts: ['Account', 'Type', 'Bank', 'Balance', 'Opened'], transactions: ['Txn ID', 'Date', 'Merchant', 'Amount', 'Status'] }

  return (
    <div style={ds.app}>
      <header style={ds.bar}><strong>⛁ DataPlatform — Records Export</strong><span style={ds.count}>{rows[tab].length} rows</span></header>
      <div style={ds.tabs}>{['customers', 'accounts', 'transactions'].map(t => <button key={t} onClick={() => setTab(t)} style={{ ...ds.tab, ...(tab === t ? ds.tabActive : {}) }}>{t}</button>)}</div>
      <div style={ds.scroll}>
        <table style={ds.table}>
          <thead><tr>{head[tab].map(h => <th key={h} style={ds.th}>{h}</th>)}</tr></thead>
          <tbody>{rows[tab].map((r, i) => <tr key={i} style={{ background: i % 2 ? '#0e1726' : 'transparent' }}>{r.map((c, j) => <td key={j} style={ds.td}>{c}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </div>
  )
}

/* ════════════════════════ 5 · RESTRICTED SESSION SANDBOX ════════════════════════ */
function RestrictedWorld({ g }) {
  const [tab, setTab] = useState('overview')
  const [blocked, setBlocked] = useState(null)
  const data = useMemo(() => ({ name: g.name(), balance: g.money(500, 80000) }), [g])
  const tryPrivileged = (label) => { setBlocked(label); setTimeout(() => setBlocked(null), 2600) }

  return (
    <div style={rs.app}>
      <div style={rs.monitor}>🛡 Limited session — actions on this account are being monitored. Re-verify your identity to restore full access.</div>
      <header style={rs.bar}><strong>◆ Meridian Trust</strong><span style={rs.badge}>RESTRICTED</span></header>
      <div style={rs.shell}>
        <nav style={rs.nav}>
          {[['overview', 'Overview', false], ['profile', 'Profile', false], ['transfers', 'Transfers', true], ['beneficiaries', 'Beneficiaries', true], ['settings', 'Settings', true]].map(([id, lbl, priv]) => (
            <button key={id} onClick={() => priv ? tryPrivileged(lbl) : setTab(id)} style={{ ...rs.navItem, ...(tab === id ? rs.navActive : {}), opacity: priv ? 0.6 : 1 }}>{lbl}{priv ? ' 🔒' : ''}</button>
          ))}
        </nav>
        <main style={rs.main}>
          {blocked && <div style={rs.block}>🔒 “{blocked}” is restricted in this session. This privileged action requires identity re-verification and has been logged.</div>}
          {tab === 'overview' && <>
            <h2 style={rs.h2}>Account Overview</h2>
            <div style={rs.card}><div style={rs.cardK}>Available balance</div><div style={rs.cardV}>{usd(data.balance)}</div></div>
            <div style={rs.note}>Transfers, beneficiary changes and settings are unavailable until you re-verify.</div>
          </>}
          {tab === 'profile' && <div style={rs.kv}>{Object.entries({ Name: data.name, Email: g.email(data.name), Phone: '+1-•••-•••-' + g.int(1000, 9999), Tier: 'Standard' }).map(([k, v]) => <div key={k} style={rs.kvRow}><span style={rs.kvK}>{k}</span><span>{v}</span></div>)}</div>}
        </main>
      </div>
    </div>
  )
}

/* ── shared little components ── */
function Stat({ t, v, accent }) { return <div style={{ ...bk.stat, ...(accent ? { borderColor: '#bcd4fb' } : {}) }}><div style={bk.statV(accent)}>{v}</div><div style={bk.statT}>{t}</div></div> }
function DStat({ t, v }) { return <div style={ad.stat}><div style={ad.statV}>{v}</div><div style={ad.statT}>{t}</div></div> }
function Table({ head, rows }) { return <table style={bk.table}><thead><tr>{head.map(h => <th key={h} style={bk.th}>{h}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} style={bk.td}>{c}</td>)}</tr>)}</tbody></table> }
function ATable({ head, rows }) { return <table style={ad.table}><thead><tr>{head.map(h => <th key={h} style={ad.th}>{h}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} style={ad.td}>{c}</td>)}</tr>)}</tbody></table> }

/* ── styles ── */
const bk = {
  app: { background: '#f4f6f9', color: '#1f2a37', borderRadius: 12, overflow: 'hidden', border: '1px solid var(--border)', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  bar: { height: 52, background: '#0b3d91', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px', fontSize: 16 },
  secure: { fontSize: 11, color: '#bfe3c9' }, shell: { display: 'flex', minHeight: 360 },
  nav: { width: 180, background: '#fff', borderRight: '1px solid #e3e8ee', padding: 12, display: 'flex', flexDirection: 'column', gap: 4 },
  navItem: { textAlign: 'left', padding: '9px 12px', border: 'none', background: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 14, color: '#3b4a5a' },
  navActive: { background: '#eaf1fd', color: '#0b5bd3', fontWeight: 600 },
  fdic: { marginTop: 'auto', fontSize: 9, color: '#9aa7b4', padding: 8 },
  main: { flex: 1, padding: '22px 26px', overflow: 'auto' }, h2: { fontSize: 20, margin: '0 0 16px' },
  cards: { display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 },
  stat: { flex: '1 1 130px', border: '1px solid #e3e8ee', borderRadius: 10, padding: '14px 16px', background: '#fff' },
  statV: (a) => ({ fontSize: 22, fontWeight: 700, color: a ? '#0b5bd3' : '#0f172a' }), statT: { fontSize: 11, color: '#6b7785', marginTop: 4 },
  alert: { padding: '10px 12px', border: '1px solid #e3e8ee', borderRadius: 8, marginBottom: 8, fontSize: 13, background: '#fff' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13, background: '#fff', border: '1px solid #e3e8ee', borderRadius: 10, overflow: 'hidden' },
  th: { textAlign: 'left', padding: '9px 12px', background: '#f7f9fc', color: '#6b7785', fontSize: 11, borderBottom: '1px solid #e3e8ee' },
  td: { padding: '9px 12px', borderBottom: '1px solid #eef2f6' }, link: { color: '#0b5bd3', textDecoration: 'none' },
}
const ad = {
  app: { display: 'flex', minHeight: 360, background: '#0f172a', color: '#e2e8f0', borderRadius: 12, overflow: 'hidden', border: '1px solid var(--border)', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  side: { width: 180, background: '#111c33', borderRight: '1px solid #1e293b', padding: 14, display: 'flex', flexDirection: 'column', gap: 4 },
  brand: { fontWeight: 700, color: '#fff', padding: '4px 8px 12px' },
  navItem: { textAlign: 'left', padding: '9px 12px', border: 'none', background: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 14, color: '#94a3b8' },
  navActive: { background: '#1d2c4d', color: '#fff', fontWeight: 600 }, foot: { marginTop: 'auto', fontSize: 9, color: '#475569', padding: 8 },
  main: { flex: 1, padding: '22px 26px', overflow: 'auto' }, h2: { fontSize: 20, margin: '0 0 16px', color: '#f1f5f9' },
  statRow: { display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 },
  stat: { flex: '1 1 120px', background: '#16233f', border: '1px solid #1e293b', borderRadius: 10, padding: '14px 16px' },
  statV: { fontSize: 22, fontWeight: 700, color: '#f1f5f9' }, statT: { fontSize: 11, color: '#94a3b8', marginTop: 4 },
  bars: { background: '#16233f', border: '1px solid #1e293b', borderRadius: 10, padding: 16, display: 'flex', flexDirection: 'column', gap: 12 },
  barRow: { display: 'flex', alignItems: 'center', gap: 10 }, barK: { width: 64, fontSize: 12, color: '#94a3b8' },
  track: { flex: 1, height: 8, background: '#1a2843', borderRadius: 99, overflow: 'hidden' }, fill: { height: '100%', borderRadius: 99 }, barV: { width: 40, fontSize: 12, textAlign: 'right' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13, background: '#16233f', border: '1px solid #1e293b', borderRadius: 10, overflow: 'hidden' },
  th: { textAlign: 'left', padding: '9px 12px', background: '#1a2843', color: '#94a3b8', fontSize: 11, borderBottom: '1px solid #1e293b' },
  td: { padding: '9px 12px', borderBottom: '1px solid #1e293b', color: '#cbd5e1' },
  roleTag: { fontSize: 11, background: '#1d2c4d', color: '#93c5fd', padding: '2px 8px', borderRadius: 6 },
  code: { fontFamily: 'monospace', fontSize: 12, color: '#7dd3fc' }, warn: { fontSize: 13, color: '#fbbf24', marginBottom: 12 },
  smallBtn: { padding: '4px 10px', border: '1px solid #334155', background: '#1a2843', color: '#cbd5e1', borderRadius: 6, cursor: 'pointer', fontSize: 12 },
  kv: { background: '#16233f', border: '1px solid #1e293b', borderRadius: 10, overflow: 'hidden' },
  kvRow: { display: 'flex', justifyContent: 'space-between', padding: '11px 16px', borderBottom: '1px solid #1e293b', fontSize: 13 }, kvK: { color: '#94a3b8' },
}
const tp = {
  app: { minHeight: 360, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(160deg,#0b1220,#141e33)', borderRadius: 12, border: '1px solid var(--border)', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  card: { width: 320, background: '#0f1830', border: '1px solid #1e2c47', borderRadius: 14, padding: 28, textAlign: 'center', boxShadow: '0 12px 40px rgba(0,0,0,.4)' },
  logo: { fontSize: 20, fontWeight: 700, color: '#e2e8f0' }, sub: { fontSize: 12, color: '#7a8aa3', margin: '6px 0 20px' },
  input: { width: '100%', padding: '11px 12px', marginBottom: 10, background: '#0b1426', border: '1px solid #243352', borderRadius: 8, color: '#cdd9e5', fontSize: 14 },
  btn: { width: '100%', padding: '11px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 14, fontWeight: 600, marginTop: 4 },
  spin: { marginTop: 14, fontSize: 12, color: '#93c5fd', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 },
  spinner: { width: 14, height: 14, borderRadius: '50%', border: '2px solid #1e2c47', borderTopColor: '#93c5fd', display: 'inline-block', animation: 'spin 0.8s linear infinite' },
  err: { marginTop: 14, fontSize: 12, color: '#fca5a5' },
  lock: { marginTop: 14, fontSize: 12, color: '#fbbf24', background: 'rgba(251,191,36,.1)', border: '1px solid rgba(251,191,36,.3)', borderRadius: 8, padding: '8px 10px' },
  foot: { marginTop: 18, fontSize: 9, color: '#48566f' },
}
const ds = {
  app: { background: '#0b1220', color: '#cdd9e5', borderRadius: 12, overflow: 'hidden', border: '1px solid var(--border)', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  bar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#111c33', color: '#e2e8f0', fontSize: 14 },
  count: { fontSize: 11, color: '#64748b' }, tabs: { display: 'flex', gap: 6, padding: '10px 16px', borderBottom: '1px solid #1e293b' },
  tab: { padding: '5px 12px', borderRadius: 6, border: '1px solid #1e293b', background: 'transparent', color: '#94a3b8', cursor: 'pointer', fontSize: 12, textTransform: 'capitalize' },
  tabActive: { background: '#1d2c4d', color: '#fff', fontWeight: 600 },
  scroll: { maxHeight: 320, overflow: 'auto' }, table: { width: '100%', borderCollapse: 'collapse', fontSize: 12 },
  th: { position: 'sticky', top: 0, textAlign: 'left', padding: '8px 12px', background: '#1a2843', color: '#94a3b8', fontSize: 11, borderBottom: '1px solid #1e293b' },
  td: { padding: '7px 12px', borderBottom: '1px solid #18243b', color: '#cbd5e1', fontFamily: 'monospace', fontSize: 11.5 },
}
const rs = {
  app: { background: '#f4f6f9', color: '#1f2a37', borderRadius: 12, overflow: 'hidden', border: '1px solid var(--border)', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  monitor: { background: 'rgba(255,184,0,.14)', color: '#7a5a00', fontSize: 12, padding: '8px 16px', borderBottom: '1px solid #f0d894' },
  bar: { height: 48, background: '#334155', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px', fontSize: 15 },
  badge: { fontSize: 10, background: '#b4232a', color: '#fff', padding: '3px 10px', borderRadius: 20, letterSpacing: 1 },
  shell: { display: 'flex', minHeight: 300 }, nav: { width: 180, background: '#fff', borderRight: '1px solid #e3e8ee', padding: 12, display: 'flex', flexDirection: 'column', gap: 4 },
  navItem: { textAlign: 'left', padding: '9px 12px', border: 'none', background: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 14, color: '#3b4a5a' },
  navActive: { background: '#eef1f5', color: '#1f2a37', fontWeight: 600 }, main: { flex: 1, padding: '22px 26px' }, h2: { fontSize: 19, margin: '0 0 14px' },
  block: { background: 'rgba(180,35,42,.08)', border: '1px solid rgba(180,35,42,.3)', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#b4232a', marginBottom: 14 },
  card: { background: '#fff', border: '1px solid #e3e8ee', borderRadius: 10, padding: 18, maxWidth: 280 }, cardK: { fontSize: 12, color: '#6b7785' }, cardV: { fontSize: 26, fontWeight: 700, marginTop: 4 },
  note: { marginTop: 14, fontSize: 13, color: '#6b7785' }, kv: { background: '#fff', border: '1px solid #e3e8ee', borderRadius: 10, overflow: 'hidden', maxWidth: 420 },
  kvRow: { display: 'flex', justifyContent: 'space-between', padding: '11px 16px', borderBottom: '1px solid #eef2f6', fontSize: 13 }, kvK: { color: '#6b7785' },
}
