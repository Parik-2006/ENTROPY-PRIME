/**
 * ComingSoon — placeholder for banking pages scheduled in Phase B
 * (Beneficiaries, Support Center, Profile). Keeps the navigation honest and
 * fully reachable while the foundation is reviewed.
 */

import { Card } from '../../components/ui'
import s from './bank.module.css'

export default function ComingSoon({ title = 'This page', icon = '🚧', children }) {
  return (
    <Card>
      <div className={s.comingWrap}>
        <div>
          <div className={s.comingIcon}>{icon}</div>
          <div className={s.comingTitle}>{title}</div>
          <div className={s.comingText}>
            {children || 'This banking surface is part of the next build. It will provide more natural typing opportunities that continuously feed the Entropy Prime behavioral engine.'}
          </div>
        </div>
      </div>
    </Card>
  )
}
