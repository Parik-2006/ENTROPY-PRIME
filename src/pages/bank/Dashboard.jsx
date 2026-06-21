/**
 * Banking Dashboard — the landing surface after enrollment.
 * Financial figures come from the frontend mock (data/bankMock.js); the
 * Security panel reflects the live Entropy Prime engine via SecurityWidget.
 */

import { Link } from 'react-router-dom'
import { Card, StatTile, ProgressBar, Button, Badge } from '../../components/ui'
import SecurityWidget from '../../components/SecurityWidget'
import TrustTimeline from '../../components/TrustTimeline'
import { useBank } from '../../context/BankContext'
import { INR, spending } from '../../data/bankMock'
import s from './bank.module.css'

const txIcon = (cat) => ({
  Income: '↓', Transfer: '⇄', Dining: '☕', Shopping: '🛍', Utilities: '⚡',
  Investment: '📈', Subscription: '▶', Groceries: '🛒',
}[cat] || '•')

export default function Dashboard() {
  const { totals, transactions } = useBank()
  const maxSpend = Math.max(...spending.map(x => x.amount))

  return (
    <div className={s.grid}>
      <div className={s.statRow}>
        <StatTile icon="₹" label="Total Balance" value={INR(totals.net)} sub="Across all accounts" trend="2.4%" />
        <StatTile icon="🏦" label="Savings" value={INR(totals.savings)} sub="High-Yield 6.8% APY" trend="0.6%" />
        <StatTile icon="📈" label="Investments" value={INR(totals.investments)} sub="Wealth Portfolio" trend="1.1%" />
        <StatTile icon="◉" label="Credit Score" value={totals.creditScore} sub="Excellent" accent="var(--accent)" />
      </div>

      <Card
        title="Trust History"
        sub="Identity confidence over this session"
        action={<Link to="/app/security"><Badge tone="ok">Security Center ↗</Badge></Link>}
      >
        <TrustTimeline height={180} />
      </Card>

      <div className={s.twoCol}>
        <Card
          title="Recent Transactions"
          action={<Link to="/app/accounts"><Button variant="ghost" size="sm">View all</Button></Link>}
        >
          <div className={s.txList}>
            {transactions.slice(0, 7).map(t => (
              <div key={t.id} className={s.txRow}>
                <div className={s.txIcon}>{txIcon(t.category)}</div>
                <div>
                  <div className={s.txMerchant}>{t.merchant}</div>
                  <div className={s.txMeta}>{t.date} · {t.category} · {t.method}</div>
                </div>
                <div className={`${s.txAmt} ${t.amount > 0 ? s.amtIn : s.amtOut}`}>
                  {t.amount > 0 ? '+' : '−'}{INR(Math.abs(t.amount)).replace('₹', '₹')}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className={s.grid}>
          <SecurityWidget />
          <Card title="Spending Overview" sub="This month">
            {spending.map(x => (
              <div key={x.category} className={s.spendRow}>
                <span className={s.spendLabel}>{x.category}</span>
                <ProgressBar value={x.amount / maxSpend} color={x.color} />
                <span className={s.spendVal}>{INR(x.amount)}</span>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </div>
  )
}
