/**
 * src/ShadowEnvironment.tsx — believable, API-driven attacker-facing UI.
 *
 * After a (synthetic) successful login the attacker lands here.  Everything on
 * screen is fetched live from the backend shadow APIs:
 *
 *   GET /api/shadow/me            → which environment (banking vs admin)
 *   GET /api/shadow/dashboard     → banking overview
 *   GET /api/shadow/accounts
 *   GET /api/shadow/transactions  (paginated)
 *   GET /api/shadow/beneficiaries
 *   GET /api/shadow/statements
 *   GET /api/shadow/profile
 *   GET /api/shadow/admin/users   (paginated)
 *   GET /api/shadow/admin/logs
 *   GET /api/shadow/admin/analytics
 *   GET /api/shadow/admin/config
 *   GET /api/shadow/admin/secrets
 *
 * REALISM CONTRACT: nothing on the attacker-facing surface may reveal the
 * deception.  The words honeypot / shadow / synthetic / decoy / canary / trap /
 * sandbox / MAB / arm / threat intelligence MUST NOT appear here.  This file
 * presents a normal online-banking app and a normal admin console.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import type { ScoreResponse, ShadowEnv } from './types'
import { fetchShadowEnv, fetchShadowAsset, fetchShadowAdmin } from './honeypotClient'

interface ShadowEnvironmentProps {
  scoreResponse: ScoreResponse
  /** Fallback to render if the shadow API is unreachable (keeps demo alive). */
  fallback?: React.ReactNode
}

// ── Generic async-data hook (loading / error / reload) ────────────────────────
function useAsset<T>(loader: () => Promise<T>, deps: unknown[]): {
  data: T | null; loading: boolean; error: string | null; reload: () => void
} {
  const [data, setData]       = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [nonce, setNonce]     = useState(0)
  const mounted = useRef(true)

  useEffect(() => () => { mounted.current = false }, [])

  useEffect(() => {
    setLoading(true); setError(null)
    loader()
      .then((d) => { if (mounted.current) { setData(d); setLoading(false) } })
      .catch((e) => { if (mounted.current) { setError(e?.message ?? 'Request failed'); setLoading(false) } })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  return { data, loading, error, reload: () => setNonce((n) => n + 1) }
}

const money = (n: number) =>
  '$' + Number(n ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// ── Top-level router: banking vs admin ────────────────────────────────────────
export function ShadowEnvironment({ scoreResponse, fallback }: ShadowEnvironmentProps) {
  const token = scoreResponse.session_token
  const { data: env, loading, error, reload } =
    useAsset<ShadowEnv>(() => fetchShadowEnv(token), [token])

  if (loading) return <FullScreenLoader label="Signing you in…" />
  if (error || !env) {
    if (fallback) return <>{fallback}</>
    return <FullScreenError onRetry={reload} />
  }
  if (env.world === 'shadow_admin') return <AdminView token={token} />
  return <BankingView token={token} />
}

/* ════════════════════════════════════════════════════════════════════════════
 *  BANKING VIEW  (light theme — looks like a real retail bank)
 * ════════════════════════════════════════════════════════════════════════════ */

const BANK_NAME = 'Meridian Trust'
type BankTab = 'overview' | 'accounts' | 'transactions' | 'payees' | 'statements' | 'profile'

const BANK_NAV: { id: BankTab; label: string; icon: string }[] = [
  { id: 'overview',     label: 'Overview',     icon: '⌂' },
  { id: 'accounts',     label: 'Accounts',     icon: '▦' },
  { id: 'transactions', label: 'Transactions', icon: '⇄' },
  { id: 'payees',       label: 'Payees',       icon: '👤' },
  { id: 'statements',   label: 'Statements',   icon: '🖹' },
  { id: 'profile',      label: 'Profile',      icon: '⚙' },
]

function BankingView({ token }: { token: string }) {
  const [tab, setTab] = useState<BankTab>('overview')
  return (
    <div style={bk.app}>
      <header style={bk.topbar}>
        <div style={bk.brand}><span style={bk.brandMark}>◆</span> {BANK_NAME}</div>
        <div style={bk.topRight}>
          <span style={bk.secure}>● Secure session</span>
          <div style={bk.avatar}>MT</div>
        </div>
      </header>
      <div style={bk.shell}>
        <nav style={bk.sidebar}>
          {BANK_NAV.map((n) => (
            <button key={n.id} onClick={() => setTab(n.id)}
              style={{ ...bk.navItem, ...(tab === n.id ? bk.navItemActive : {}) }}>
              <span style={bk.navIcon}>{n.icon}</span> {n.label}
            </button>
          ))}
          <div style={bk.navFooter}>FDIC insured · Member FDIC</div>
        </nav>
        <main style={bk.content}>
          {tab === 'overview'     && <BankOverview token={token} />}
          {tab === 'accounts'     && <BankAccounts token={token} />}
          {tab === 'transactions' && <BankTransactions token={token} />}
          {tab === 'payees'       && <BankPayees token={token} />}
          {tab === 'statements'   && <BankStatements token={token} />}
          {tab === 'profile'      && <BankProfile token={token} />}
        </main>
      </div>
    </div>
  )
}

function BankOverview({ token }: { token: string }) {
  const { data, loading, error, reload } = useAsset<any>(() => fetchShadowAsset('dashboard', token), [token])
  if (loading) return <PanelLoader />
  if (error)   return <PanelError onRetry={reload} />
  return (
    <div>
      <h1 style={bk.h1}>{data.greeting}</h1>
      <div style={bk.cardRow}>
        <Stat title="Total balance" value={money(data.net_worth)} accent />
        <Stat title="Open accounts" value={String(data.accounts_count)} />
        <Stat title="Pending items" value={String(data.pending_count)} />
      </div>
      <h2 style={bk.h2}>Notifications</h2>
      <div style={bk.alertList}>
        {(data.alerts ?? []).map((a: any, i: number) => (
          <div key={i} style={bk.alert}><span style={bk.alertDot}>i</span>{a.text}</div>
        ))}
      </div>
    </div>
  )
}

function BankAccounts({ token }: { token: string }) {
  const { data, loading, error, reload } = useAsset<any>(() => fetchShadowAsset('accounts', token), [token])
  if (loading) return <PanelLoader />
  if (error)   return <PanelError onRetry={reload} />
  return (
    <div>
      <h1 style={bk.h1}>Accounts</h1>
      <div style={bk.summaryBar}>Combined balance <strong>{money(data.total_balance)}</strong></div>
      <div style={bk.accountGrid}>
        {data.accounts.map((a: any) => (
          <div key={a.account_id} style={bk.accountCard}>
            <div style={bk.accountType}>{a.type}</div>
            <div style={bk.accountBank}>{a.bank}</div>
            <div style={bk.accountBalance}>{money(a.balance)}</div>
            <div style={bk.accountMeta}>•••• {String(a.account_id).slice(-4)} · {a.currency}</div>
            <span style={bk.accountStatus}>{a.status}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function BankTransactions({ token }: { token: string }) {
  const [page, setPage] = useState(1)
  const pageSize = 15
  const { data, loading, error, reload } =
    useAsset<any>(() => fetchShadowAsset('transactions', token, { page, page_size: pageSize }), [token, page])
  return (
    <div>
      <h1 style={bk.h1}>Transactions</h1>
      {loading ? <PanelLoader /> : error ? <PanelError onRetry={reload} /> : (
        <>
          <table style={bk.table}>
            <thead><tr>{['Date', 'Description', 'Category', 'Status', 'Amount'].map((h) =>
              <th key={h} style={bk.th}>{h}</th>)}</tr></thead>
            <tbody>
              {data.transactions.map((t: any) => (
                <tr key={t.txn_id} style={bk.row}>
                  <td style={bk.td}>{t.date}</td>
                  <td style={bk.td}>{t.merchant}</td>
                  <td style={bk.td}><span style={bk.tag}>{t.category}</span></td>
                  <td style={bk.td}>{t.status}</td>
                  <td style={{ ...bk.td, textAlign: 'right', color: t.amount < 0 ? '#b4232a' : '#137333', fontVariantNumeric: 'tabular-nums' }}>
                    {t.amount < 0 ? '-' : '+'}{money(Math.abs(t.amount))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager page={page} hasMore={!!data.has_more} onPrev={() => setPage((p) => Math.max(1, p - 1))} onNext={() => setPage((p) => p + 1)} />
        </>
      )}
    </div>
  )
}

function BankPayees({ token }: { token: string }) {
  const { data, loading, error, reload } = useAsset<any>(() => fetchShadowAsset('beneficiaries', token), [token])
  if (loading) return <PanelLoader />
  if (error)   return <PanelError onRetry={reload} />
  return (
    <div>
      <h1 style={bk.h1}>Payees</h1>
      <div style={bk.payeeGrid}>
        {data.beneficiaries.map((b: any) => (
          <div key={b.beneficiary_id} style={bk.payeeCard}>
            <div style={bk.payeeAvatar}>{String(b.name).split(' ').map((s: string) => s[0]).join('').slice(0, 2)}</div>
            <div>
              <div style={bk.payeeName}>{b.nickname}</div>
              <div style={bk.payeeMeta}>{b.name} · {b.bank}</div>
              <div style={bk.payeeMeta}>•••• {String(b.account_number).slice(-4)} · last sent {b.last_transfer}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function BankStatements({ token }: { token: string }) {
  const { data, loading, error, reload } = useAsset<any>(() => fetchShadowAsset('statements', token), [token])
  if (loading) return <PanelLoader />
  if (error)   return <PanelError onRetry={reload} />
  return (
    <div>
      <h1 style={bk.h1}>Statements</h1>
      <table style={bk.table}>
        <thead><tr>{['Period', 'Opening', 'Closing', 'Document'].map((h) => <th key={h} style={bk.th}>{h}</th>)}</tr></thead>
        <tbody>
          {data.statements.map((s: any) => (
            <tr key={s.statement_id} style={bk.row}>
              <td style={bk.td}>{s.period}</td>
              <td style={bk.td}>{money(s.opening)}</td>
              <td style={bk.td}>{money(s.closing)}</td>
              <td style={bk.td}><a style={bk.link} href="#" onClick={(e) => e.preventDefault()}>⬇ {s.document}</a></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BankProfile({ token }: { token: string }) {
  const { data, loading, error, reload } = useAsset<any>(() => fetchShadowAsset('profile', token), [token])
  if (loading) return <PanelLoader />
  if (error)   return <PanelError onRetry={reload} />
  const c = data.customer
  return (
    <div>
      <h1 style={bk.h1}>Profile</h1>
      <div style={bk.profileCard}>
        {[
          ['Name', c.name], ['Email', c.email], ['Phone', c.phone],
          ['Address', c.address], ['SSN', c.ssn], ['Customer since', c.customer_since],
          ['Membership', c.tier],
        ].map(([k, v]) => (
          <div key={k as string} style={bk.profileRow}>
            <span style={bk.profileKey}>{k}</span><span style={bk.profileVal}>{v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════════════════
 *  ADMIN VIEW  (clean dark SaaS console)
 * ════════════════════════════════════════════════════════════════════════════ */

const ADMIN_NAME = 'Console'
type AdminTab = 'dashboard' | 'users' | 'logs' | 'analytics' | 'config' | 'secrets'
const ADMIN_NAV: { id: AdminTab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'users',     label: 'Users' },
  { id: 'logs',      label: 'Audit Logs' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'config',    label: 'Settings' },
  { id: 'secrets',   label: 'API Keys' },
]

function AdminView({ token }: { token: string }) {
  const [tab, setTab] = useState<AdminTab>('dashboard')
  return (
    <div style={ad.app}>
      <aside style={ad.sidebar}>
        <div style={ad.brand}>▣ {ADMIN_NAME}</div>
        {ADMIN_NAV.map((n) => (
          <button key={n.id} onClick={() => setTab(n.id)}
            style={{ ...ad.navItem, ...(tab === n.id ? ad.navItemActive : {}) }}>{n.label}</button>
        ))}
        <div style={ad.sidebarFoot}>v4.2.1 · prod</div>
      </aside>
      <main style={ad.main}>
        {tab === 'dashboard' && <AdminDashboard token={token} />}
        {tab === 'users'     && <AdminUsers token={token} />}
        {tab === 'logs'      && <AdminLogs token={token} />}
        {tab === 'analytics' && <AdminAnalytics token={token} />}
        {tab === 'config'    && <AdminConfig token={token} />}
        {tab === 'secrets'   && <AdminSecrets token={token} />}
      </main>
    </div>
  )
}

function AdminDashboard({ token }: { token: string }) {
  const { data, loading, error, reload } = useAsset<any>(() => fetchShadowAdmin('dashboard', token), [token])
  if (loading) return <PanelLoader dark />
  if (error)   return <PanelError dark onRetry={reload} />
  return (
    <div>
      <h1 style={ad.h1}>Dashboard</h1>
      <div style={ad.statRow}>
        <DStat title="Active users" value={Number(data.active_users).toLocaleString()} />
        <DStat title="Open tickets" value={String(data.open_tickets)} />
        <DStat title="Uptime" value={`${data.uptime_days} days`} />
        <DStat title="Version" value={data.version} />
      </div>
      <div style={ad.systemRow}>
        System <strong style={{ color: '#34d399' }}>{data.status}</strong> · cluster {data.system}
      </div>
    </div>
  )
}

function AdminUsers({ token }: { token: string }) {
  const [page, setPage] = useState(1)
  const pageSize = 15
  const { data, loading, error, reload } =
    useAsset<any>(() => fetchShadowAdmin('users', token, { page, page_size: pageSize }), [token, page])
  return (
    <div>
      <h1 style={ad.h1}>Users</h1>
      {loading ? <PanelLoader dark /> : error ? <PanelError dark onRetry={reload} /> : (
        <>
          <table style={ad.table}>
            <thead><tr>{['Name', 'Email', 'Role', 'Status', 'Last login', 'MFA'].map((h) =>
              <th key={h} style={ad.th}>{h}</th>)}</tr></thead>
            <tbody>
              {data.users.map((u: any) => (
                <tr key={u.user_id} style={ad.row}>
                  <td style={ad.td}>{u.name}</td>
                  <td style={ad.td}>{u.email}</td>
                  <td style={ad.td}><span style={ad.roleTag}>{u.role}</span></td>
                  <td style={ad.td}><span style={{ ...ad.statusTag, color: u.status === 'active' ? '#34d399' : '#fbbf24' }}>{u.status}</span></td>
                  <td style={ad.td}>{u.last_login}</td>
                  <td style={ad.td}>{u.mfa ? 'on' : 'off'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager dark page={page} hasMore={!!data.has_more} onPrev={() => setPage((p) => Math.max(1, p - 1))} onNext={() => setPage((p) => p + 1)} />
        </>
      )}
    </div>
  )
}

function AdminLogs({ token }: { token: string }) {
  const { data, loading, error, reload } = useAsset<any>(() => fetchShadowAdmin('logs', token), [token])
  if (loading) return <PanelLoader dark />
  if (error)   return <PanelError dark onRetry={reload} />
  return (
    <div>
      <h1 style={ad.h1}>Audit Logs</h1>
      <table style={ad.table}>
        <thead><tr>{['Time', 'Actor', 'Action', 'IP', 'Result'].map((h) => <th key={h} style={ad.th}>{h}</th>)}</tr></thead>
        <tbody>
          {data.logs.map((l: any, i: number) => (
            <tr key={i} style={ad.row}>
              <td style={ad.td}>{l.ts}</td>
              <td style={ad.td}>{l.actor}</td>
              <td style={ad.td}><code style={ad.code}>{l.action}</code></td>
              <td style={ad.td}>{l.ip}</td>
              <td style={{ ...ad.td, color: l.result === 'ok' ? '#34d399' : '#f87171' }}>{l.result}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AdminAnalytics({ token }: { token: string }) {
  const { data, loading, error, reload } = useAsset<any>(() => fetchShadowAdmin('analytics', token), [token])
  if (loading) return <PanelLoader dark />
  if (error)   return <PanelError dark onRetry={reload} />
  const max = Math.max(...data.revenue_series.map((m: any) => m.revenue), 1)
  return (
    <div>
      <h1 style={ad.h1}>Analytics</h1>
      <div style={ad.statRow}>
        <DStat title="MRR" value={money(data.mrr)} />
        <DStat title="Active subscriptions" value={Number(data.active_subscriptions).toLocaleString()} />
      </div>
      <div style={ad.chart}>
        {data.revenue_series.map((m: any) => (
          <div key={m.month} style={ad.barWrap} title={`${m.month}: ${money(m.revenue)}`}>
            <div style={{ ...ad.bar, height: `${Math.round((m.revenue / max) * 100)}%` }} />
            <div style={ad.barLabel}>{m.month.slice(5)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function AdminConfig({ token }: { token: string }) {
  const { data, loading, error, reload } = useAsset<any>(() => fetchShadowAdmin('config', token), [token])
  if (loading) return <PanelLoader dark />
  if (error)   return <PanelError dark onRetry={reload} />
  return (
    <div>
      <h1 style={ad.h1}>Settings</h1>
      <h2 style={ad.h2}>Feature flags</h2>
      <div style={ad.kvList}>
        {Object.entries(data.feature_flags).map(([k, v]) => (
          <div key={k} style={ad.kvRow}>
            <span>{k}</span>
            <span style={{ color: v ? '#34d399' : '#64748b' }}>{v ? 'enabled' : 'disabled'}</span>
          </div>
        ))}
      </div>
      <h2 style={ad.h2}>Integrations</h2>
      <div style={ad.kvList}>
        {Object.entries(data.integrations).map(([k, v]) => (
          <div key={k} style={ad.kvRow}><span>{k}</span><code style={ad.code}>{String(v)}</code></div>
        ))}
      </div>
      <h2 style={ad.h2}>Regions</h2>
      <div style={ad.kvRow}><span>active</span><span>{(data.regions ?? []).join(', ')}</span></div>
    </div>
  )
}

function AdminSecrets({ token }: { token: string }) {
  const { data, loading, error, reload } = useAsset<any>(() => fetchShadowAdmin('secrets', token), [token])
  const [shown, setShown] = useState<Record<string, boolean>>({})
  if (loading) return <PanelLoader dark />
  if (error)   return <PanelError dark onRetry={reload} />
  return (
    <div>
      <h1 style={ad.h1}>API Keys</h1>
      <p style={ad.subtle}>{data.warning}</p>
      <table style={ad.table}>
        <thead><tr>{['Name', 'Value', ''].map((h) => <th key={h} style={ad.th}>{h}</th>)}</tr></thead>
        <tbody>
          {data.secrets.map((s: any) => (
            <tr key={s.name} style={ad.row}>
              <td style={ad.td}><code style={ad.code}>{s.name}</code></td>
              <td style={ad.td}>
                <code style={{ ...ad.code, color: '#e2e8f0' }}>
                  {shown[s.name] ? s.value : '•'.repeat(Math.min(28, String(s.value).length))}
                </code>
              </td>
              <td style={ad.td}>
                <button style={ad.smallBtn} onClick={() => setShown((p) => ({ ...p, [s.name]: !p[s.name] }))}>
                  {shown[s.name] ? 'Hide' : 'Reveal'}
                </button>
                <button style={ad.smallBtn} onClick={() => navigator.clipboard?.writeText(String(s.value))}>Copy</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── Shared presentational primitives ───────────────────────────────────────── */

function Stat({ title, value, accent }: { title: string; value: string; accent?: boolean }) {
  return (
    <div style={{ ...bk.statCard, ...(accent ? bk.statCardAccent : {}) }}>
      <div style={bk.statTitle}>{title}</div>
      <div style={{ ...bk.statValue, color: accent ? '#0b5bd3' : '#0f172a' }}>{value}</div>
    </div>
  )
}
function DStat({ title, value }: { title: string; value: string }) {
  return (
    <div style={ad.statCard}>
      <div style={ad.statTitle}>{title}</div>
      <div style={ad.statValue}>{value}</div>
    </div>
  )
}
function Pager({ page, hasMore, onPrev, onNext, dark }: { page: number; hasMore: boolean; onPrev: () => void; onNext: () => void; dark?: boolean }) {
  const btn = dark ? ad.pagerBtn : bk.pagerBtn
  const wrap = dark ? ad.pager : bk.pager
  return (
    <div style={wrap}>
      <button style={{ ...btn, opacity: page <= 1 ? 0.4 : 1 }} disabled={page <= 1} onClick={onPrev}>‹ Prev</button>
      <span style={dark ? ad.pagerLabel : bk.pagerLabel}>Page {page}</span>
      <button style={{ ...btn, opacity: hasMore ? 1 : 0.4 }} disabled={!hasMore} onClick={onNext}>Next ›</button>
    </div>
  )
}

function Spinner({ dark }: { dark?: boolean }) {
  return <div style={{
    width: 22, height: 22, borderRadius: '50%',
    border: `2px solid ${dark ? '#1e293b' : '#dbe2ea'}`,
    borderTopColor: dark ? '#38bdf8' : '#0b5bd3',
    animation: 'spin 0.7s linear infinite',
  }} />
}
function FullScreenLoader({ label }: { label: string }) {
  return <div style={fs.center}><Spinner /><div style={fs.label}>{label}</div></div>
}
function FullScreenError({ onRetry }: { onRetry: () => void }) {
  return (
    <div style={fs.center}>
      <div style={fs.errTitle}>We're having trouble connecting</div>
      <div style={fs.errSub}>Please check your connection and try again.</div>
      <button style={fs.retry} onClick={onRetry}>Try again</button>
    </div>
  )
}
function PanelLoader({ dark }: { dark?: boolean }) {
  return <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 40, color: dark ? '#64748b' : '#64748b' }}><Spinner dark={dark} /> Loading…</div>
}
function PanelError({ onRetry, dark }: { onRetry: () => void; dark?: boolean }) {
  return (
    <div style={{ padding: 24, color: dark ? '#cbd5e1' : '#475569' }}>
      <div style={{ marginBottom: 10 }}>Unable to load this section right now.</div>
      <button style={dark ? ad.smallBtn : bk.pagerBtn} onClick={onRetry}>Retry</button>
    </div>
  )
}

/* ── Styles ──────────────────────────────────────────────────────────────────
 * Banking = light retail-bank theme.  Admin = dark SaaS console.  Two clearly
 * distinct, ordinary-looking products — neither hints at deception.            */

const fs: Record<string, React.CSSProperties> = {
  center: { minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, background: '#f4f6f9', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  label: { color: '#5b6b7d', fontSize: 14 },
  errTitle: { fontSize: 18, fontWeight: 600, color: '#1f2a37' },
  errSub: { fontSize: 13, color: '#6b7785' },
  retry: { marginTop: 8, padding: '9px 20px', background: '#0b5bd3', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 },
}

const bk: Record<string, React.CSSProperties> = {
  app: { minHeight: '100vh', background: '#f4f6f9', color: '#1f2a37', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  topbar: { height: 60, background: '#0b3d91', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px' },
  brand: { fontSize: 18, fontWeight: 700, letterSpacing: 0.3, display: 'flex', alignItems: 'center', gap: 8 },
  brandMark: { color: '#9fc0ff' },
  topRight: { display: 'flex', alignItems: 'center', gap: 16 },
  secure: { fontSize: 12, color: '#bfe3c9' },
  avatar: { width: 34, height: 34, borderRadius: '50%', background: '#08306b', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700 },
  shell: { display: 'flex', minHeight: 'calc(100vh - 60px)' },
  sidebar: { width: 220, background: '#fff', borderRight: '1px solid #e3e8ee', padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: 4 },
  navItem: { display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', border: 'none', background: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 14, color: '#3b4a5a', textAlign: 'left', width: '100%' },
  navItemActive: { background: '#eaf1fd', color: '#0b5bd3', fontWeight: 600 },
  navIcon: { width: 18, textAlign: 'center', opacity: 0.8 },
  navFooter: { marginTop: 'auto', fontSize: 10, color: '#9aa7b4', padding: '12px 8px' },
  content: { flex: 1, padding: '28px 36px', overflowY: 'auto' },
  h1: { fontSize: 24, fontWeight: 700, margin: '0 0 20px' },
  h2: { fontSize: 15, fontWeight: 600, margin: '28px 0 12px', color: '#3b4a5a' },
  cardRow: { display: 'flex', gap: 16, flexWrap: 'wrap' },
  statCard: { flex: '1 1 180px', background: '#fff', border: '1px solid #e3e8ee', borderRadius: 12, padding: '18px 20px' },
  statCardAccent: { borderColor: '#bcd4fb', background: 'linear-gradient(180deg,#f5f9ff,#fff)' },
  statTitle: { fontSize: 12, color: '#6b7785', marginBottom: 8 },
  statValue: { fontSize: 26, fontWeight: 700, fontVariantNumeric: 'tabular-nums' },
  alertList: { display: 'flex', flexDirection: 'column', gap: 8 },
  alert: { display: 'flex', alignItems: 'center', gap: 10, background: '#fff', border: '1px solid #e3e8ee', borderRadius: 8, padding: '12px 14px', fontSize: 13, color: '#3b4a5a' },
  alertDot: { width: 18, height: 18, borderRadius: '50%', background: '#eaf1fd', color: '#0b5bd3', fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', fontStyle: 'italic', fontWeight: 700 },
  summaryBar: { fontSize: 13, color: '#6b7785', marginBottom: 16 },
  accountGrid: { display: 'flex', gap: 16, flexWrap: 'wrap' },
  accountCard: { width: 230, background: '#fff', border: '1px solid #e3e8ee', borderRadius: 12, padding: 18 },
  accountType: { fontSize: 15, fontWeight: 700 },
  accountBank: { fontSize: 12, color: '#6b7785', marginBottom: 14 },
  accountBalance: { fontSize: 24, fontWeight: 700, fontVariantNumeric: 'tabular-nums' },
  accountMeta: { fontSize: 12, color: '#6b7785', marginTop: 6 },
  accountStatus: { display: 'inline-block', marginTop: 12, fontSize: 11, color: '#137333', background: '#e6f4ea', padding: '2px 10px', borderRadius: 20 },
  table: { width: '100%', borderCollapse: 'collapse', background: '#fff', border: '1px solid #e3e8ee', borderRadius: 12, overflow: 'hidden', fontSize: 13 },
  th: { textAlign: 'left', padding: '12px 14px', background: '#f7f9fc', color: '#6b7785', fontSize: 12, fontWeight: 600, borderBottom: '1px solid #e3e8ee' },
  row: { borderBottom: '1px solid #eef2f6' },
  td: { padding: '12px 14px', color: '#2b3744' },
  tag: { fontSize: 11, background: '#f0f3f7', color: '#52606d', padding: '2px 8px', borderRadius: 6 },
  link: { color: '#0b5bd3', textDecoration: 'none' },
  payeeGrid: { display: 'flex', flexDirection: 'column', gap: 10 },
  payeeCard: { display: 'flex', alignItems: 'center', gap: 14, background: '#fff', border: '1px solid #e3e8ee', borderRadius: 10, padding: '14px 16px' },
  payeeAvatar: { width: 40, height: 40, borderRadius: '50%', background: '#eaf1fd', color: '#0b5bd3', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13 },
  payeeName: { fontSize: 14, fontWeight: 600 },
  payeeMeta: { fontSize: 12, color: '#6b7785' },
  profileCard: { background: '#fff', border: '1px solid #e3e8ee', borderRadius: 12, maxWidth: 560, overflow: 'hidden' },
  profileRow: { display: 'flex', justifyContent: 'space-between', padding: '13px 18px', borderBottom: '1px solid #eef2f6' },
  profileKey: { color: '#6b7785', fontSize: 13 },
  profileVal: { fontSize: 13, fontWeight: 500 },
  pager: { display: 'flex', alignItems: 'center', gap: 14, marginTop: 16 },
  pagerBtn: { padding: '7px 14px', border: '1px solid #cdd7e1', background: '#fff', borderRadius: 7, cursor: 'pointer', fontSize: 13, color: '#2b3744' },
  pagerLabel: { fontSize: 13, color: '#6b7785' },
}

const ad: Record<string, React.CSSProperties> = {
  app: { minHeight: '100vh', display: 'flex', background: '#0f172a', color: '#e2e8f0', fontFamily: "'Segoe UI', system-ui, sans-serif" },
  sidebar: { width: 220, background: '#111c33', borderRight: '1px solid #1e293b', padding: 16, display: 'flex', flexDirection: 'column', gap: 4 },
  brand: { fontSize: 16, fontWeight: 700, color: '#fff', padding: '6px 10px 16px' },
  navItem: { textAlign: 'left', padding: '10px 12px', border: 'none', background: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 14, color: '#94a3b8', width: '100%' },
  navItemActive: { background: '#1d2c4d', color: '#fff', fontWeight: 600 },
  sidebarFoot: { marginTop: 'auto', fontSize: 10, color: '#475569', padding: '12px 10px' },
  main: { flex: 1, padding: '28px 36px', overflowY: 'auto' },
  h1: { fontSize: 24, fontWeight: 700, margin: '0 0 20px', color: '#f1f5f9' },
  h2: { fontSize: 14, fontWeight: 600, margin: '24px 0 10px', color: '#94a3b8' },
  statRow: { display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 14 },
  statCard: { flex: '1 1 160px', background: '#16233f', border: '1px solid #1e293b', borderRadius: 12, padding: '16px 18px' },
  statTitle: { fontSize: 12, color: '#94a3b8', marginBottom: 8 },
  statValue: { fontSize: 24, fontWeight: 700, color: '#f1f5f9', fontVariantNumeric: 'tabular-nums' },
  systemRow: { fontSize: 13, color: '#94a3b8', background: '#16233f', border: '1px solid #1e293b', borderRadius: 10, padding: '12px 16px' },
  table: { width: '100%', borderCollapse: 'collapse', background: '#16233f', border: '1px solid #1e293b', borderRadius: 12, overflow: 'hidden', fontSize: 13 },
  th: { textAlign: 'left', padding: '11px 14px', background: '#1a2843', color: '#94a3b8', fontSize: 12, fontWeight: 600, borderBottom: '1px solid #1e293b' },
  row: { borderBottom: '1px solid #1e293b' },
  td: { padding: '11px 14px', color: '#cbd5e1' },
  roleTag: { fontSize: 11, background: '#1d2c4d', color: '#93c5fd', padding: '2px 8px', borderRadius: 6 },
  statusTag: { fontSize: 12, fontWeight: 600 },
  code: { fontFamily: 'monospace', fontSize: 12, color: '#7dd3fc' },
  subtle: { fontSize: 13, color: '#94a3b8', marginBottom: 14 },
  smallBtn: { padding: '5px 10px', border: '1px solid #334155', background: '#1a2843', color: '#cbd5e1', borderRadius: 6, cursor: 'pointer', fontSize: 12, marginRight: 6 },
  kvList: { background: '#16233f', border: '1px solid #1e293b', borderRadius: 10, overflow: 'hidden' },
  kvRow: { display: 'flex', justifyContent: 'space-between', padding: '11px 16px', borderBottom: '1px solid #1e293b', fontSize: 13 },
  chart: { display: 'flex', alignItems: 'flex-end', gap: 10, height: 200, background: '#16233f', border: '1px solid #1e293b', borderRadius: 12, padding: 20, marginTop: 14 },
  barWrap: { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%', gap: 6 },
  bar: { width: '70%', background: 'linear-gradient(180deg,#38bdf8,#0ea5e9)', borderRadius: '4px 4px 0 0', minHeight: 4 },
  barLabel: { fontSize: 10, color: '#64748b' },
  pager: { display: 'flex', alignItems: 'center', gap: 14, marginTop: 16 },
  pagerBtn: { padding: '7px 14px', border: '1px solid #334155', background: '#1a2843', color: '#cbd5e1', borderRadius: 7, cursor: 'pointer', fontSize: 13 },
  pagerLabel: { fontSize: 13, color: '#94a3b8' },
}
