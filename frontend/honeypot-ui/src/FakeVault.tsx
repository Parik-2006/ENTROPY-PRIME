/**
 * src/FakeVault.tsx — Shadow-mode fake data vault UI.
 *
 * Presents convincing-looking (but entirely synthetic) "admin data" to bots
 * that have been shadow-routed. All data is fabricated; nothing here touches
 * a real database or exposes real user information.
 *
 * The goal is to keep the bot engaged while the MAB reward timer runs, and to
 * harvest additional automation signatures via the invisible decoys injected
 * by the DecoyRenderer layer beneath this component.
 *
 * Arm-adaptive content:
 *   Arm 0 (Tarpit)  → heavy form with fake user records + edit forms
 *   Arm 1 (Echo)    → mirrored "API response" JSON with subtly wrong field names
 *   Arm 2 (Canary)  → minimal read-only table with canary tokens embedded
 */

import React, { useMemo } from 'react'
import type { ScoreResponse } from './types'

interface FakeVaultProps {
  scoreResponse: ScoreResponse
}

// ── Synthetic data generators ────────────────────────────────────────────────

function fakeToken(seed: string): string {
  const chars = 'abcdef0123456789'
  let h = 0x811c9dc5
  for (const c of seed) { h ^= c.charCodeAt(0); h = Math.imul(h, 0x01000193) >>> 0 }
  return Array.from({ length: 32 }, (_, i) => chars[(h ^ (i * 17)) % 16]).join('')
}

function fakeEmail(n: number): string {
  const names = ['alice', 'bob', 'charlie', 'diana', 'eve', 'frank', 'grace', 'henry']
  const domains = ['acme.io', 'stripe.com', 'shopify.com', 'vercel.app']
  return `${names[n % names.length]}${n}@${domains[n % domains.length]}`
}

interface FakeUser {
  id: string
  email: string
  role: string
  status: string
  apiKey: string
  created: string
}

function generateFakeUsers(count = 8): FakeUser[] {
  const roles   = ['admin', 'operator', 'viewer', 'auditor']
  const statuses = ['active', 'active', 'active', 'suspended']
  return Array.from({ length: count }, (_, i) => ({
    id:      `uid_${fakeToken(`user${i}`).slice(0, 8)}`,
    email:   fakeEmail(i),
    role:    roles[i % roles.length],
    status:  statuses[i % statuses.length],
    apiKey:  `ep_live_${fakeToken(`key${i}`)}`,
    created: new Date(Date.now() - i * 86_400_000 * 7).toISOString().split('T')[0],
  }))
}

// ── Arm 0: Tarpit — heavy form with fake user records ───────────────────────

function TarpitView({ users }: { users: FakeUser[] }) {
  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>USER MANAGEMENT — {users.length} RECORDS</div>
      <table style={styles.table}>
        <thead>
          <tr>
            {['ID', 'Email', 'Role', 'Status', 'API Key', 'Created', 'Actions'].map((h) => (
              <th key={h} style={styles.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} style={styles.tr}>
              <td style={styles.td}><code style={styles.code}>{u.id}</code></td>
              <td style={styles.td}>{u.email}</td>
              <td style={styles.td}>
                <span style={{ ...styles.badge, color: u.role === 'admin' ? '#ff3b5c' : '#00e5ff' }}>
                  {u.role}
                </span>
              </td>
              <td style={styles.td}>
                <span style={{ ...styles.badge, color: u.status === 'active' ? '#00ffa3' : '#ffb800' }}>
                  {u.status}
                </span>
              </td>
              <td style={styles.td}>
                <code style={{ ...styles.code, fontSize: 9 }}>{u.apiKey.slice(0, 24)}•••</code>
              </td>
              <td style={styles.td}>{u.created}</td>
              <td style={styles.td}>
                {/* Fake action buttons — bots may click these */}
                <button style={styles.actionBtn}>Edit</button>
                <button style={{ ...styles.actionBtn, color: '#ff3b5c', marginLeft: 4 }}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Arm 1: Echo — mirrored API response with wrong field names ───────────────

function EchoView({ users }: { users: FakeUser[] }) {
  // Field names are subtly mutated (like the Echo arm decoys in stage2_honeypot.py)
  const payload = {
    sucess: true,           // typo: should be "success"
    usres: users.slice(0, 4).map((u) => ({
      usr_id:     u.id,
      usernmae:   u.email,  // typo: mirrors "usernmae" decoy field
      acces_role: u.role,   // typo
      api_tolen:  u.apiKey, // typo: "tolen" instead of "token"
    })),
    totel: users.length,    // typo: "totel" instead of "total"
    _canary: fakeToken('canary_echo'),
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>API RESPONSE MIRROR — /api/v1/users</div>
      <pre style={styles.jsonBlock}>{JSON.stringify(payload, null, 2)}</pre>
      <div style={{ ...styles.sectionTitle, marginTop: 16 }}>RAW HEADERS</div>
      <pre style={styles.jsonBlock}>{[
        'HTTP/1.1 200 OK',
        'Content-Type: application/json',
        `X-Request-Id: ${fakeToken('reqid')}`,
        `X-Canary-Token: ${fakeToken('canary_hdr')}`,
        'X-Rate-Limit-Remaining: 9994',
        'Cache-Control: no-store',
      ].join('\n')}</pre>
    </div>
  )
}

// ── Arm 2: Canary — minimal read-only table with embedded canary tokens ──────

function CanaryView({ users }: { users: FakeUser[] }) {
  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>AUDIT LOG — LAST 5 EVENTS</div>
      <table style={styles.table}>
        <thead>
          <tr>
            {['Timestamp', 'User', 'Action', 'Canary Token'].map((h) => (
              <th key={h} style={styles.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {users.slice(0, 5).map((u, i) => (
            <tr key={u.id} style={styles.tr}>
              <td style={styles.td}>{new Date(Date.now() - i * 3_600_000).toISOString()}</td>
              <td style={styles.td}>{u.email}</td>
              <td style={styles.td}>LOGIN_SUCCESS</td>
              <td style={styles.td}>
                <code style={{ ...styles.code, color: '#ffb800', fontSize: 9 }}>
                  {fakeToken(`canary_${u.id}`)}
                </code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={styles.canaryNote}>
        ⚠ Canary tokens embedded above are monitored. Any exfiltration will be detected.
      </div>
    </div>
  )
}

// ── Main FakeVault ────────────────────────────────────────────────────────────

export function FakeVault({ scoreResponse }: FakeVaultProps) {
  const arm   = scoreResponse.mab_arm ?? 0
  const users = useMemo(() => generateFakeUsers(8), [])

  return (
    <div style={styles.vault}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <div style={styles.logo}>EP</div>
          <div>
            <div style={styles.title}>ENTROPY PRIME — Admin Vault</div>
            <div style={styles.subtitle}>
              Shadow sandbox · Arm {arm} · Session {scoreResponse.session_token.slice(0, 20)}•••
            </div>
          </div>
        </div>
        <div style={styles.statusPill}>
          <div style={{ ...styles.dot, background: '#00ffa3' }} />
          AUTHENTICATED
        </div>
      </div>

      {/* Arm-adaptive content */}
      {arm === 0 && <TarpitView users={users} />}
      {arm === 1 && <EchoView   users={users} />}
      {arm === 2 && <CanaryView users={users} />}
    </div>
  )
}

// ── Inline styles ─────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  vault: {
    background: '#080b0f',
    minHeight: '100vh',
    color: '#c9d6e3',
    fontFamily: "'Syne', 'Segoe UI', sans-serif",
  },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '16px 24px',
    background: '#0d1117',
    borderBottom: '1px solid #1e2d3d',
  },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 14 },
  logo: {
    width: 40, height: 40, border: '1.5px solid #00e5ff',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontFamily: 'monospace', fontSize: 12, fontWeight: 700, color: '#00e5ff',
  },
  title:    { fontSize: 15, fontWeight: 700, letterSpacing: 2 },
  subtitle: { fontSize: 10, color: '#6b8299', marginTop: 2, fontFamily: 'monospace' },
  statusPill: {
    display: 'flex', alignItems: 'center', gap: 7,
    padding: '6px 14px', background: 'rgba(0,255,163,.08)',
    border: '1px solid rgba(0,255,163,.2)', borderRadius: 20,
    fontSize: 10, color: '#00ffa3', fontFamily: 'monospace', letterSpacing: 1,
  },
  dot: { width: 7, height: 7, borderRadius: '50%' },
  section: { padding: '20px 24px' },
  sectionTitle: {
    fontFamily: 'monospace', fontSize: 9, letterSpacing: 2,
    color: '#3a5068', marginBottom: 12,
  },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 11 },
  th: {
    padding: '8px 10px', textAlign: 'left' as const,
    background: '#111820', borderBottom: '1px solid #1e2d3d',
    fontFamily: 'monospace', fontSize: 9, letterSpacing: 1, color: '#6b8299',
  },
  tr: { borderBottom: '1px solid #1e2d3d' },
  td: { padding: '10px 10px', verticalAlign: 'middle' as const },
  badge: {
    padding: '2px 8px', borderRadius: 3,
    fontFamily: 'monospace', fontSize: 9, letterSpacing: 1,
    background: 'rgba(0,229,255,0.06)',
  },
  code: { fontFamily: 'monospace', color: '#00e5ff' },
  actionBtn: {
    padding: '4px 8px', background: 'none',
    border: '1px solid #1e2d3d', borderRadius: 3,
    color: '#6b8299', fontSize: 10, cursor: 'pointer',
  },
  jsonBlock: {
    background: '#0d1117', border: '1px solid #1e2d3d',
    borderRadius: 6, padding: '12px 14px',
    fontFamily: 'monospace', fontSize: 10, color: '#00ffa3',
    whiteSpace: 'pre-wrap', overflowX: 'auto',
    lineHeight: 1.6,
  },
  canaryNote: {
    marginTop: 12, padding: '8px 12px',
    background: 'rgba(255,184,0,.06)', border: '1px solid rgba(255,184,0,.2)',
    borderRadius: 4, fontSize: 10, color: '#ffb800', fontFamily: 'monospace',
  },
}
