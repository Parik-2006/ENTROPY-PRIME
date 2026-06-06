/**
 * src/useHoneypot.ts — React hook: bridge between main app and Stage 2 layer.
 *
 * The main app (src/pages/LoginPage.jsx) already calls submitScore() from
 * src/services/api.js. This hook wraps that existing flow and adds the
 * Stage 2 honeypot lifecycle ON TOP — no rewrite of the main app needed.
 *
 * Usage (add to LoginPage.jsx or AuthContext.jsx):
 *
 *   import { useHoneypot } from '../honeypot-ui/src/useHoneypot'
 *
 *   const { applyScoreResponse, shadowMode, decoyManager } = useHoneypot({
 *     sessionToken: authData.session_token,
 *     onDecoyTriggered: (decoyId, kind, event) => {
 *       console.log('Bot caught!', { decoyId, kind, event })
 *     },
 *   })
 *
 *   // After loginUser() + submitScore() succeed:
 *   applyScoreResponse(scoreData)
 *
 *   // In JSX: if shadowMode, replace UI with <ShadowDashboard>
 *
 * The hook is safe to call unconditionally — when shadow_mode=false it is
 * a no-op (no DOM mutations, no network calls beyond the normal flow).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { ScoreResponse } from './types'
import { DecoyManager } from './DecoyRenderer'
import { reportMabReward } from './honeypotClient'

const MAB_REWARD_DELAY_MS = 8_000

export interface UseHoneypotOptions {
  /** Active session token (from /auth/login or /auth/register) */
  sessionToken: string
  /** Called once when any decoy is first interacted with */
  onDecoyTriggered?: (decoyId: string, kind: string, event: string) => void
  /** Called when the shadow session ends (expired / cleanup) */
  onShadowEnded?: () => void
}

export interface UseHoneypotReturn {
  /** Feed the /score response into the honeypot layer */
  applyScoreResponse: (res: ScoreResponse) => void
  /** True after a shadow_mode=true response has been applied */
  shadowMode: boolean
  /** The last applied /score response (null before first call) */
  lastResponse: ScoreResponse | null
  /** Number of decoy trigger events so far */
  triggerCount: number
  /** Tear down all active challenges (call on logout / unmount) */
  destroyAll: () => void
}

export function useHoneypot(opts: UseHoneypotOptions): UseHoneypotReturn {
  const [shadowMode,    setShadowMode]    = useState(false)
  const [lastResponse,  setLastResponse]  = useState<ScoreResponse | null>(null)
  const [triggerCount,  setTriggerCount]  = useState(0)

  // Stable refs so callbacks don't go stale
  const sessionTokenRef = useRef(opts.sessionToken)
  useEffect(() => { sessionTokenRef.current = opts.sessionToken }, [opts.sessionToken])

  const onTriggeredRef = useRef(opts.onDecoyTriggered)
  useEffect(() => { onTriggeredRef.current = opts.onDecoyTriggered }, [opts.onDecoyTriggered])

  const onEndedRef = useRef(opts.onShadowEnded)
  useEffect(() => { onEndedRef.current = opts.onShadowEnded }, [opts.onShadowEnded])

  // Singleton DecoyManager per hook instance
  const managerRef    = useRef<DecoyManager | null>(null)
  const rewardTimers  = useRef<ReturnType<typeof setTimeout>[]>([])

  // Initialise manager once
  if (!managerRef.current) {
    managerRef.current = new DecoyManager()
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      managerRef.current?.destroyAll()
      rewardTimers.current.forEach(clearTimeout)
    }
  }, [])

  const applyScoreResponse = useCallback((res: ScoreResponse) => {
    setLastResponse(res)

    if (!res.shadow_mode || !res.challenge) {
      // Human path — nothing to do for Stage 2
      setShadowMode(false)
      return
    }

    setShadowMode(true)

    // Apply challenge → inject decoys
    managerRef.current!.applyChallenge(res.challenge, {
      sessionToken: sessionTokenRef.current,
      onTriggered: (decoyId, kind, event) => {
        setTriggerCount((c) => c + 1)
        onTriggeredRef.current?.(decoyId, kind, event)
      },
      onDestroyed: (reason) => {
        if (reason === 'expired' || reason === 'cleanup') {
          onEndedRef.current?.()
        }
      },
    })

    // Schedule MAB reward closure
    const arm    = res.mab_arm ?? 0
    const timerId = setTimeout(() => {
      // Positive reward: challenge ran its course = deception held
      reportMabReward(arm, 0.5)
    }, MAB_REWARD_DELAY_MS)
    rewardTimers.current.push(timerId)
  }, [])

  const destroyAll = useCallback(() => {
    managerRef.current?.destroyAll()
    setShadowMode(false)
    rewardTimers.current.forEach(clearTimeout)
    rewardTimers.current = []
  }, [])

  return { applyScoreResponse, shadowMode, lastResponse, triggerCount, destroyAll }
}
