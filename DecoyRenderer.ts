/**
 * src/DecoyRenderer.ts — DOM-level decoy injection & event monitoring.
 *
 * This module is the browser-side counterpart of:
 *   backend/models/stage2_honeypot.py  (arm strategies, DecoySpec)
 *   public/sdk/entropy.js              (HoneypotEngine class)
 *
 * It mirrors the same invisibility strategy used by the SDK:
 *   1. position: absolute; left: -99999px  (off-canvas)
 *   2. opacity: 0; visibility: hidden       (invisible to humans)
 *   3. width: 0; height: 0                  (zero-size)
 *   4. tabindex="-1"                         (keyboard-unreachable)
 *   5. aria-hidden="true"                   (screen-reader hidden)
 *   6. pointer-events: none                 (cannot be accidentally clicked)
 *
 * Bots that programmatically fill/click DOM elements trigger all monitored
 * events (focus, input, change, click); real users never reach them.
 *
 * One DecoyRenderer instance manages a single ChallengeConfig lifecycle:
 *   inject() → monitoring → onTriggered callback → destroy()
 */

import type { ChallengeConfig, DecoySpec, TriggerRequest } from './types'
import { reportTrigger } from './honeypotClient'

const CONTAINER_ID  = '__ep_hp_container__'
const STYLE_ID      = '__ep_hp_style__'
const DECOY_PREFIX  = '__ep_d_'

// Events monitored on each decoy element
const WATCHED_EVENTS: string[] = ['focus', 'input', 'change', 'click', 'blur']

export interface DecoyRendererOptions {
  /** Called once when any decoy is first interacted with */
  onTriggered?: (decoyId: string, kind: string, event: string) => void
  /** Called when the challenge expires or is destroyed */
  onDestroyed?: (reason: 'triggered' | 'expired' | 'cleanup') => void
  /** Active session token (required for trigger POST) */
  sessionToken: string
}

export class DecoyRenderer {
  private readonly _challenge: ChallengeConfig
  private readonly _opts: DecoyRendererOptions
  private _decoyEls: HTMLElement[] = []
  private _triggered = false
  private _expiryTimer: ReturnType<typeof setTimeout> | null = null

  constructor(challenge: ChallengeConfig, opts: DecoyRendererOptions) {
    this._challenge = challenge
    this._opts      = opts
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Inject invisible decoys into the DOM and begin monitoring.
   * Safe to call multiple times — idempotent.
   */
  inject(): void {
    if (this._decoyEls.length) return  // already injected

    this._ensureStyle()
    const container = this._ensureContainer()

    for (const spec of this._challenge.decoys) {
      const wrapper = this._buildDecoy(spec)
      if (wrapper) {
        container.appendChild(wrapper)
        this._decoyEls.push(wrapper)
      }
    }

    // Auto-destroy when TTL expires
    const msUntilExpiry = Math.max(0, this._challenge.expires_at * 1000 - Date.now())
    this._expiryTimer = setTimeout(() => this.destroy('expired'), msUntilExpiry)

    console.debug(
      `[DecoyRenderer] Injected ${this._decoyEls.length} decoys for challenge`,
      this._challenge.challenge_id,
      `arm=${this._challenge.arm}`,
      `ttl=${Math.round(msUntilExpiry / 1000)}s`,
    )
  }

  /** Remove all decoys and cancel monitoring */
  destroy(reason: 'triggered' | 'expired' | 'cleanup' = 'cleanup'): void {
    if (this._expiryTimer) { clearTimeout(this._expiryTimer); this._expiryTimer = null }
    for (const el of this._decoyEls) {
      try { el.parentNode?.removeChild(el) } catch { /* ignore */ }
    }
    this._decoyEls = []
    this._opts.onDestroyed?.(reason)
    console.debug(`[DecoyRenderer] Destroyed challenge ${this._challenge.challenge_id} (${reason})`)
  }

  get challengeId(): string { return this._challenge.challenge_id }
  get arm(): number          { return this._challenge.arm }
  get triggered(): boolean   { return this._triggered }

  // ── Private: DOM helpers ────────────────────────────────────────────────────

  private _buildDecoy(spec: DecoySpec): HTMLElement | null {
    const wrapper = document.createElement('div')
    wrapper.setAttribute('aria-hidden', 'true')
    wrapper.setAttribute('role', 'presentation')
    // Five-layer invisibility stack (matches SDK HoneypotEngine)
    wrapper.style.cssText = [
      'position:absolute',
      'left:-99999px',
      'top:-99999px',
      'width:0',
      'height:0',
      'overflow:hidden',
      'opacity:0',
      'visibility:hidden',
      'pointer-events:none',
      'z-index:-9999',
    ].join(';')

    let inner: HTMLElement | null = null

    switch (spec.kind) {
      case 'input': {
        const el = document.createElement('input')
        el.type         = spec.autocomplete?.includes('password') ? 'password' : 'text'
        el.name         = spec.name
        el.id           = `${DECOY_PREFIX}${spec.decoy_id}`
        el.setAttribute('autocomplete', spec.autocomplete || 'off')
        el.tabIndex     = spec.tab_index ?? -1
        inner = el
        break
      }
      case 'checkbox': {
        const el = document.createElement('input')
        el.type     = 'checkbox'
        el.name     = spec.name
        el.id       = `${DECOY_PREFIX}${spec.decoy_id}`
        el.tabIndex = spec.tab_index ?? -1
        inner = el
        break
      }
      case 'button': {
        const el = document.createElement('button')
        el.type        = 'button'
        el.name        = spec.name
        el.id          = `${DECOY_PREFIX}${spec.decoy_id}`
        el.tabIndex    = spec.tab_index ?? -1
        el.textContent = spec.label
        inner = el
        break
      }
      case 'link': {
        const el = document.createElement('a')
        el.href        = '#'
        el.id          = `${DECOY_PREFIX}${spec.decoy_id}`
        el.tabIndex    = spec.tab_index ?? -1
        el.textContent = spec.label
        // Prevent navigation
        el.addEventListener('click', (e) => e.preventDefault())
        inner = el as unknown as HTMLElement
        break
      }
      default:
        return null
    }

    if (!inner) return null

    // Hidden label (for semantic completeness — screen readers excluded via aria-hidden)
    const lbl = document.createElement('label')
    lbl.htmlFor     = `${DECOY_PREFIX}${spec.decoy_id}`
    lbl.textContent = spec.label
    lbl.style.cssText = 'position:absolute;left:-99999px;opacity:0'
    wrapper.appendChild(lbl)

    // Attach event listeners — fire on first interaction
    WATCHED_EVENTS.forEach((evtName) => {
      inner!.addEventListener(evtName, (evt) => {
        evt.preventDefault?.()
        this._onInteraction(spec, evtName)
      })
    })

    wrapper.appendChild(inner)
    return wrapper
  }

  private _onInteraction(spec: DecoySpec, eventType: string): void {
    if (this._triggered) return  // fire exactly once per challenge

    this._triggered = true
    this._opts.onTriggered?.(spec.decoy_id, spec.kind, eventType)

    // Build trigger request matching HoneypotTriggerReq in main.py
    const req: TriggerRequest = {
      challenge_id:    this._challenge.challenge_id,
      arm:             this._challenge.arm,
      expires_at:      this._challenge.expires_at,
      signature:       this._challenge.signature,
      decoy_ids:       this._challenge.decoys.map((d) => d.decoy_id),
      triggered_decoy: spec.decoy_id,
      trigger_event:   eventType,
      trigger_kind:    spec.kind,
      session_token:   this._opts.sessionToken,
    }

    // Fire-and-forget — never blocks or throws into caller
    reportTrigger(req)

    // Self-destruct immediately after trigger
    this.destroy('triggered')
  }

  // ── Private: style / container helpers ────────────────────────────────────

  private _ensureStyle(): void {
    if (document.getElementById(STYLE_ID)) return
    const style = document.createElement('style')
    style.id = STYLE_ID
    // Belt-and-suspenders CSS — high-specificity ID selector intentional
    style.textContent = `
      #${CONTAINER_ID},
      #${CONTAINER_ID} * {
        position: absolute !important;
        left: -99999px !important;
        top: -99999px !important;
        width: 0 !important;
        height: 0 !important;
        opacity: 0 !important;
        visibility: hidden !important;
        overflow: hidden !important;
        pointer-events: none !important;
        user-select: none !important;
        clip: rect(0,0,0,0) !important;
      }
    `.trim()
    ;(document.head || document.documentElement).appendChild(style)
  }

  private _ensureContainer(): HTMLElement {
    let container = document.getElementById(CONTAINER_ID)
    if (!container) {
      container = document.createElement('div')
      container.id = CONTAINER_ID
      container.setAttribute('aria-hidden', 'true')
      container.setAttribute('role', 'presentation')
      document.body.appendChild(container)
    }
    return container
  }
}

/**
 * DecoyManager: manages multiple concurrent challenge lifecycles.
 *
 * The main app calls applyChallenge() whenever a /score response contains
 * a challenge field with shadow_mode=true. Multiple challenges can be active
 * simultaneously (different browser tabs, rapid re-scoring), but each
 * challenge_id is deduplicated.
 */
export class DecoyManager {
  private _renderers = new Map<string, DecoyRenderer>()

  applyChallenge(challenge: ChallengeConfig, opts: DecoyRendererOptions): void {
    if (this._renderers.has(challenge.challenge_id)) {
      console.debug('[DecoyManager] Duplicate challenge ignored:', challenge.challenge_id)
      return
    }

    const renderer = new DecoyRenderer(challenge, {
      ...opts,
      onDestroyed: (reason) => {
        this._renderers.delete(challenge.challenge_id)
        opts.onDestroyed?.(reason)
      },
    })

    this._renderers.set(challenge.challenge_id, renderer)
    renderer.inject()
  }

  destroyAll(): void {
    for (const renderer of this._renderers.values()) {
      renderer.destroy('cleanup')
    }
    this._renderers.clear()
  }

  get activeChallengeCount(): number { return this._renderers.size }
}
