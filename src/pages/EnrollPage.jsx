/**
 * EnrollPage — Behavioral Enrollment
 * ----------------------------------
 * Replaces the old "type random text" ProfileBuildPage UX with a natural,
 * guided onboarding flow. The user answers friendly prompts; the biometric
 * engine silently learns their interaction style (dwell/flight/rhythm/mouse).
 *
 * IMPORTANT: this reuses the *exact same* data path as the legacy ProfileBuild
 * page — getBiometricCollector → evaluate → submitScore → syncBiometricProfile
 * (with requested_state:'stable' at threshold) → confirmStable. No biometric
 * logic is reimplemented; only the presentation changes.
 *
 * Readiness model (fixes the dead-end bug):
 *   completion = min(sampleProgress, wordProgress)  → 100% ⟺ fully ready.
 *   When completion hits 100% (or the server confirms `stable`) we IMMEDIATELY
 *   switch to the success state — there is no state where the bar reads 100% /
 *   "Established" while the user is still told to keep typing. The success
 *   screen offers an instant "Continue Now" CTA plus a 3-second auto-redirect.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useAuth,
  ONBOARDING_STABLE,
  ONBOARDING_DRIFTED,
} from '../context/AuthContext'
import { submitScore, syncBiometricProfile } from '../services/api'
import { getBiometricCollector, resetBiometricCollector } from '../services/biometricCollector'
import { Button, TextArea, ProgressBar, Badge, ThemeToggle } from '../components/ui'
import s from './Enroll.module.css'

const TARGET = 50            // behavioral samples for a stable baseline (backend-aligned)
const WORD_TARGET = 100      // minimum words across all prompts
const SEC_PER_SAMPLE = 2.2
const REDIRECT_SECONDS = 3

const QUESTIONS = [
  { q: 'Tell us a little about yourself.',           hint: 'Where you live, what you do — anything that feels natural to write.' },
  { q: 'Describe a hobby you genuinely enjoy.',      hint: 'What got you into it? What do you love about it?' },
  { q: 'Share a memorable experience or trip.',      hint: 'A place, a moment, a story worth a few sentences.' },
  { q: 'What are some goals you’re working toward?',  hint: 'Personal or professional — write as much as you like.' },
  { q: 'Write freely about anything for a moment.',   hint: 'No prompt this time — just type comfortably.' },
]

const countWords = (str) => (str.trim() ? str.trim().split(/\s+/).filter(Boolean).length : 0)

function strengthLabel(p) {
  if (p >= 1)    return { label: 'Established', tone: 'ok' }
  if (p >= 0.66) return { label: 'Strong', tone: 'ok' }
  if (p >= 0.33) return { label: 'Developing', tone: 'warn' }
  return { label: 'Forming', tone: 'neutral' }
}

function etaText(remainingSamples, remainingWords) {
  if (remainingSamples <= 0 && remainingWords <= 0) return 'Ready'
  const secs = Math.max(Math.round(remainingSamples * SEC_PER_SAMPLE), Math.round(remainingWords * 0.6))
  if (secs <= 0) return 'Almost there…'
  if (secs >= 60) return `~${Math.ceil(secs / 60)} min remaining`
  return `~${secs}s remaining`
}

export default function EnrollPage() {
  const navigate = useNavigate()
  const {
    user, getClient, epReady, liveTheta,
    onboardingState, isProfileStable, confirmStable, profileStats,
  } = useAuth()

  const [step, setStep]       = useState(0)
  const [answers, setAnswers] = useState(['', '', '', '', ''])
  const [collState, setCollState] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [countdown, setCountdown] = useState(REDIRECT_SECONDS)

  const syncTimer = useRef(null)
  const lastSynced = useRef('')
  const collectorRef = useRef(null)

  useEffect(() => { collectorRef.current = getBiometricCollector() }, [])
  useEffect(() => { if (!user) navigate('/login') }, [user, navigate])

  // ── Readiness math ─────────────────────────────────────────────────────────
  const localSamples  = collState?.collectedSamples ?? 0
  const serverSamples = profileStats?.sampleCount ?? 0
  const samples = Math.max(localSamples, serverSamples)
  const totalWords = answers.reduce((n, a) => n + countWords(a), 0)

  const sampleProgress = Math.min(samples / TARGET, 1)
  const wordProgress   = Math.min(totalWords / WORD_TARGET, 1)
  // Completion reflects BOTH requirements — so 100% can only mean "done".
  const completion = Math.min(sampleProgress, wordProgress)
  const remainingSamples = Math.max(0, TARGET - samples)
  const remainingWords   = Math.max(0, WORD_TARGET - totalWords)

  const confidence = Math.round(completion * 100)
  const strength = strengthLabel(completion)

  // Ready when both gates are satisfied, OR the server already promoted us.
  const ready = (completion >= 1) || isProfileStable || onboardingState === ONBOARDING_STABLE
  const showSuccess = ready

  const text = answers[step]
  const setText = (val) => setAnswers(prev => prev.map((a, i) => (i === step ? val : a)))

  // Promote local onboarding state the moment requirements are met so the rest
  // of the app (trust-gated transfers, routing) treats the profile as stable.
  useEffect(() => {
    if (ready && !isProfileStable) confirmStable()
  }, [ready, isProfileStable, confirmStable])

  // ── Auto-redirect countdown once successful ────────────────────────────────
  useEffect(() => {
    if (!showSuccess) return
    setCountdown(REDIRECT_SECONDS)
    const id = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) { clearInterval(id); navigate('/app/dashboard'); return 0 }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(id)
  }, [showSuccess, navigate])

  // ── Debounced collect + sync (mirrors ProfileBuildPage) ────────────────────
  useEffect(() => {
    if (!user || !epReady || showSuccess) return
    const typed = text.trim()
    if (typed.length < 10) return
    if (typed === lastSynced.current) return
    if (onboardingState === ONBOARDING_DRIFTED) return

    if (syncTimer.current) clearTimeout(syncTimer.current)
    syncTimer.current = setTimeout(async () => {
      const ep = getClient()
      if (!ep || !collectorRef.current) return
      try {
        setSyncing(true)
        const { theta, hExp } = await ep.evaluate(typed)
        const latentVector = await ep.getLatentVector()
        const kb = ep.getKeyboardStats()
        const pt = ep.getPointerStats()
        const liveStats = ep.getProfileStats()

        collectorRef.current.addSample({
          theta, hExp,
          dwell: kb?.avgDwell ?? 0, flight: kb?.avgFlight ?? 0, rhythm: kb?.rhythm ?? 0,
          speed: pt?.avgSpeed ?? 0, jitter: pt?.avgJitter ?? 0, accel: pt?.avgAccel ?? 0,
          pause: kb?.avgPause ?? 0,
        })
        const cs = collectorRef.current.getState()
        setCollState(cs)

        await submitScore({ theta, hExp, latentVector, serverLoad: 0.35 })

        const { payload, samplesInPayload } = collectorRef.current.buildSyncPayload(
          theta, hExp, latentVector, liveStats,
        )
        if (cs.collectedSamples >= TARGET) payload.requested_state = 'stable'

        const res = await syncBiometricProfile(payload)
        if (samplesInPayload > 0) collectorRef.current.markPersisted(samplesInPayload)

        const serverState = res?.profile_status?.onboarding_state
        if (serverState === ONBOARDING_STABLE && !isProfileStable) confirmStable()

        lastSynced.current = typed
      } catch (err) {
        console.error('[EnrollPage] sync failed:', err)
      } finally {
        setSyncing(false)
      }
    }, 1200)

    return () => { if (syncTimer.current) clearTimeout(syncTimer.current) }
  }, [text, user, epReady, showSuccess, getClient, onboardingState, isProfileStable, confirmStable])

  const handleReset = useCallback(() => {
    resetBiometricCollector()
    collectorRef.current = getBiometricCollector()
    setCollState(null)
    setAnswers(['', '', '', '', ''])
    setStep(0)
    lastSynced.current = ''
  }, [])

  // ── Success screen ─────────────────────────────────────────────────────────
  if (showSuccess) {
    const summary = [
      ['Typing Rhythm', 'Collected', 'ok'],
      ['Pause Patterns', 'Collected', 'ok'],
      ['Interaction Profile', 'Established', 'ok'],
      ['Behavioral Confidence', `${Math.max(confidence, 90)}%`, 'ok'],
    ]
    return (
      <div className={s.page}>
        <Left />
        <div className={s.right}>
          <div className={s.card}>
            <div className={s.successWrap}>
              <div className={s.successMark}>✓</div>
              <div className={s.successTitle}>Behavioral Profile Established</div>
              <div className={s.successText}>
                Your behavioral baseline has been securely created. From now on, your identity is
                continuously verified in the background — no extra steps, no friction.
              </div>

              <div className={s.summaryBox}>
                {summary.map(([k, v, tone]) => (
                  <div className={s.summaryRow} key={k}>
                    <span className={s.summaryKey}>{k}</span>
                    <Badge tone={tone} dot>{v}</Badge>
                  </div>
                ))}
              </div>

              <Button size="lg" full onClick={() => navigate('/app/dashboard')}>
                Continue to Entropy Bank →
              </Button>
              <div className={s.countdown}>
                Redirecting automatically in {countdown}s
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ── Enrollment flow ────────────────────────────────────────────────────────
  const current = QUESTIONS[step]
  const canAdvance = step < QUESTIONS.length - 1

  let primaryLabel = 'Next prompt →'
  let primaryAction = () => setStep(step + 1)
  let primaryDisabled = false
  if (!canAdvance) {
    // last prompt and not ready yet → guide the user on what's missing
    primaryLabel = remainingWords > 0
      ? `Write ${remainingWords} more word${remainingWords === 1 ? '' : 's'}`
      : 'Keep typing to finish'
    primaryDisabled = true
    primaryAction = () => {}
  }

  return (
    <div className={s.page}>
      <Left />
      <div className={s.right}>
        <div className={s.card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
            <Badge tone={strength.tone} dot>Profile {strength.label}</Badge>
            <ThemeToggle />
          </div>

          <div className={s.steps}>
            {QUESTIONS.map((_, i) => (
              <div key={i} className={`${s.stepDot} ${i === step ? s.stepActive : ''} ${i < step ? s.stepDone : ''}`} />
            ))}
          </div>

          <div className={s.qIndex}>QUESTION {step + 1} / {QUESTIONS.length}</div>
          <div className={s.question}>{current.q}</div>
          <div className={s.qHint}>{current.hint}</div>

          <TextArea
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder="Start typing naturally…"
            style={{ minHeight: 130 }}
            autoFocus
          />

          {/* Word counter — always visible so users know how much is required */}
          <div className={s.wordRow}>
            <span className={s.learning}>
              <span className={s.learnPulse} style={{ background: syncing ? 'var(--accent)' : 'var(--text-3)' }} />
              {epReady ? 'Learning your interaction rhythm…' : 'Preparing secure enrollment…'}
            </span>
            <span className={s.wordCount}>
              Words: <strong style={{ color: 'var(--text)' }}>{totalWords}</strong> / {WORD_TARGET}
              {remainingWords > 0 && <span className={s.wordRemain}> · {remainingWords} to go</span>}
            </span>
          </div>

          <div className={s.meterRow}>
            <span className={s.meterLabel}>Behavioral profile completion</span>
            <span className={s.meterVal}>{Math.round(completion * 100)}%</span>
          </div>
          <ProgressBar value={completion} tone={completion >= 1 ? 'ok' : 'warn'} />
          <div className={s.metaRow}>
            <span>Strength: {strength.label} · Confidence {confidence}%</span>
            <span>{etaText(remainingSamples, remainingWords)}</span>
          </div>

          <div className={s.actions}>
            <Button variant="ghost" onClick={handleReset}>Start over</Button>
            <Button full variant="primary" onClick={primaryAction} disabled={primaryDisabled}>
              {primaryLabel}
            </Button>
          </div>

          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 18, lineHeight: 1.6 }}>
            🔒 We measure <em>how</em> you type, never <em>what</em> you type. Raw keystrokes never
            leave your browser.
          </div>
        </div>
      </div>
    </div>
  )
}

function Left() {
  return (
    <div className={s.left}>
      <div className={s.brand}>
        <div className={s.logoMark}>EB</div>
        <div>
          <div className={s.brandName}>ENTROPY BANK</div>
          <div className={s.brandSub}>Protected by Entropy Prime</div>
        </div>
      </div>

      <div>
        <div className={s.headline}>Before we protect your account, we’ll learn how you interact.</div>
        <div className={s.lede}>
          Entropy Prime builds a private behavioral signature from your natural typing and pointer
          rhythm. It’s what lets us tell <strong>you</strong> apart from anyone else — even on the
          same device — without passwords getting in the way.
        </div>

        <div className={s.assured}>
          <div className={s.assureItem}>
            <div className={s.assureIcon}>⌨</div>
            <div>
              <div className={s.assureTitle}>Just answer naturally</div>
              <div className={s.assureDesc}>A few friendly prompts — no “random text” to type.</div>
            </div>
          </div>
          <div className={s.assureItem}>
            <div className={s.assureIcon}>🔒</div>
            <div>
              <div className={s.assureTitle}>Private by design</div>
              <div className={s.assureDesc}>Only timing patterns are analyzed, never your words.</div>
            </div>
          </div>
          <div className={s.assureItem}>
            <div className={s.assureIcon}>♾</div>
            <div>
              <div className={s.assureTitle}>Continuous protection</div>
              <div className={s.assureDesc}>Your identity is re-verified silently, every session.</div>
            </div>
          </div>
        </div>
      </div>

      <div className={s.footnote}>Entropy Prime — behavioral security framework · Phases 1–4 active</div>
    </div>
  )
}
