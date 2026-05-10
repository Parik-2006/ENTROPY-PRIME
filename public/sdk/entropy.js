/**
 * entropy.js — Entropy Prime SDK  v2.0.0
 * =======================================
 *
 * Drop-in behavioural biometrics + honeypot SDK.
 *
 * Quick start
 * ───────────
 *   <script src="/sdk/entropy.js"></script>
 *   <script>
 *     const ep = new EntropySDK({ apiKey: "ep_live_…", endpoint: "https://api.example.com" });
 *     ep.init();
 *   </script>
 *
 * What it does
 * ────────────
 * 1. Collects passive biometric signals (mouse dynamics, keystroke cadence,
 *    scroll rhythm, touch pressure) via non-blocking event listeners.
 * 2. On init() — and periodically thereafter — calls /score with a latent
 *    behavioural vector.
 * 3. If the /score response contains a `challenge` payload the SDK:
 *      a. Injects invisible DOM decoys (inputs, buttons, links, checkboxes)
 *         that are imperceptible to humans but detectable by bots.
 *      b. Monitors each decoy for: focus, input, change, click, submit.
 *      c. On any interaction, fires a signed /honeypot/trigger report and
 *         immediately self-destructs all decoys for that challenge.
 * 4. Sends /session/verify heartbeats while a session is active.
 * 5. On /session/verify → FORCE_LOGOUT: clears the local session and fires
 *    the onForceLogout callback.
 *
 * Bot-evasion notes (what makes decoys work)
 * ───────────────────────────────────────────
 * • Decoys are rendered with legitimate HTML attributes bots scan for:
 *   realistic name=, autocomplete=, type=, id= values.
 * • Visual invisibility uses five independent methods so a bot cannot
 *   bypass one and still interact safely:
 *     1. position: absolute; left: -9999px; top: -9999px  (off-canvas)
 *     2. opacity: 0; visibility: hidden                   (invisible)
 *     3. width: 0; height: 0; overflow: hidden            (zero-size)
 *     4. tabindex="-1"                                     (not keyboard-reachable)
 *     5. aria-hidden="true"                               (screen-reader hidden)
 * • All five must be bypassed simultaneously for a human to interact accidentally.
 *   Real users never do this; bots that programmatically fill/click DOM elements do.
 * • The challenge signature is validated server-side on /honeypot/trigger so
 *   bots cannot replay or forge trigger events to poison the MAB.
 *
 * Architecture
 * ────────────
 *
 *   ┌─────────────────────────────────────────────────────────────┐
 *   │  EntropySDK                                                 │
 *   │  ├── BiometricCollector  (event listeners → latent vector)  │
 *   │  ├── HoneypotEngine      (inject → monitor → report)       │
 *   │  ├── SessionManager      (token, heartbeat, logout)         │
 *   │  └── Transport           (fetch wrapper, retry, queue)      │
 *   └─────────────────────────────────────────────────────────────┘
 */

(function (global) {
  "use strict";

  // ── Constants ───────────────────────────────────────────────────────────────

  const SDK_VERSION       = "2.0.0";
  const SCORE_INTERVAL_MS = 30_000;   // re-score every 30 s
  const HEARTBEAT_MS      = 20_000;   // /session/verify every 20 s
  const LATENT_DIM        = 32;       // must match backend BiometricInput
  const DECOY_STYLE_ID    = "__ep_decoy_style__";
  const DECOY_CONTAINER_ID= "__ep_decoys__";
  const DECOY_PREFIX      = "__ep_d_";

  // ── Utilities ───────────────────────────────────────────────────────────────

  function noop() {}

  function safeJSON(text) {
    try { return JSON.parse(text); } catch { return null; }
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  /** Deterministic hash of a string → float in [0, 1] (for latent seeding). */
  function hashToFloat(str) {
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = (h * 0x01000193) >>> 0;
    }
    return (h >>> 0) / 0xFFFFFFFF;
  }

  function uuid() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
  }


  // ══════════════════════════════════════════════════════════════════════════
  // BiometricCollector
  // Passively accumulates behavioural signals into a normalised 32-dim vector.
  // ══════════════════════════════════════════════════════════════════════════

  class BiometricCollector {
    constructor() {
      this._mouse  = { dx: 0, dy: 0, samples: 0, speed: 0 };
      this._scroll = { delta: 0, events: 0 };
      this._keys   = { intervals: [], lastDown: 0 };
      this._touch  = { force: 0, samples: 0 };
      this._clicks = 0;
      this._focus  = { switches: 0, lastSwitch: Date.now() };
      this._bound  = {};
      this._active = false;
    }

    start() {
      if (this._active) return;
      this._active = true;

      const add = (el, ev, fn, opts) => {
        this._bound[ev] = fn;
        el.addEventListener(ev, fn, opts || { passive: true });
      };

      add(document, "mousemove", (e) => {
        this._mouse.dx      += Math.abs(e.movementX || 0);
        this._mouse.dy      += Math.abs(e.movementY || 0);
        this._mouse.samples += 1;
        // Micro-jitter detection: real mice have non-zero variance
        this._mouse.speed = Math.sqrt(
          (e.movementX || 0) ** 2 + (e.movementY || 0) ** 2
        );
      });

      add(document, "keydown", (e) => {
        const now = Date.now();
        if (this._keys.lastDown > 0) {
          const interval = now - this._keys.lastDown;
          if (interval < 2000) {           // ignore long pauses
            this._keys.intervals.push(interval);
            if (this._keys.intervals.length > 50) this._keys.intervals.shift();
          }
        }
        this._keys.lastDown = now;
      });

      add(document, "scroll", () => {
        this._scroll.delta  += window.scrollY;
        this._scroll.events += 1;
      });

      add(document, "click", () => { this._clicks += 1; });

      add(document, "touchstart", (e) => {
        const touches = e.touches;
        for (let i = 0; i < touches.length; i++) {
          const t = touches[i];
          if (t.force !== undefined) {
            this._touch.force   += t.force;
            this._touch.samples += 1;
          }
        }
      });

      add(window, "focus", () => {
        this._focus.switches += 1;
        this._focus.lastSwitch = Date.now();
      });
    }

    stop() {
      if (!this._active) return;
      this._active = false;
      for (const [ev, fn] of Object.entries(this._bound)) {
        try {
          document.removeEventListener(ev, fn, { passive: true });
          window.removeEventListener(ev, fn, { passive: true });
        } catch {}
      }
    }

    /**
     * Derive a 32-dim latent vector from accumulated signals.
     *
     * Layout (indices):
     *   0–3   Mouse dynamics  (dx, dy, speed, sample count normalised)
     *   4–5   Scroll          (delta, event count)
     *   6–9   Keystroke IKI   (mean, std-dev, min, max intervals normalised)
     *  10     Click count
     *  11–12  Touch           (mean force, sample count)
     *  13     Focus switches
     *  14     Time on page (log-scaled)
     *  15–16  User-agent hash components
     *  17–31  Zero-padded (reserved for future signals)
     */
    snapshot() {
      const vec = new Array(LATENT_DIM).fill(0.0);
      const m   = this._mouse;
      const s   = this._scroll;
      const k   = this._keys;
      const t   = this._touch;

      // Mouse
      vec[0] = clamp(m.dx / 10000, 0, 1);
      vec[1] = clamp(m.dy / 10000, 0, 1);
      vec[2] = clamp(m.speed / 50,  0, 1);
      vec[3] = clamp(m.samples / 1000, 0, 1);

      // Scroll
      vec[4] = clamp(Math.abs(s.delta) / 5000, 0, 1);
      vec[5] = clamp(s.events / 200, 0, 1);

      // Keystroke inter-key intervals (IKI)
      if (k.intervals.length > 0) {
        const mean = k.intervals.reduce((a, b) => a + b, 0) / k.intervals.length;
        const variance = k.intervals.reduce((a, b) => a + (b - mean) ** 2, 0) / k.intervals.length;
        vec[6] = clamp(mean / 500, 0, 1);
        vec[7] = clamp(Math.sqrt(variance) / 200, 0, 1);
        vec[8] = clamp(Math.min(...k.intervals) / 500, 0, 1);
        vec[9] = clamp(Math.max(...k.intervals) / 2000, 0, 1);
      }

      // Clicks
      vec[10] = clamp(this._clicks / 100, 0, 1);

      // Touch
      vec[11] = t.samples > 0 ? clamp(t.force / t.samples, 0, 1) : 0;
      vec[12] = clamp(t.samples / 50, 0, 1);

      // Focus
      vec[13] = clamp(this._focus.switches / 20, 0, 1);

      // Time on page
      vec[14] = clamp(Math.log(1 + performance.now() / 1000) / 10, 0, 1);

      // UA hash components (two independent hashes for richer signal)
      const ua = navigator.userAgent || "";
      vec[15]  = hashToFloat(ua);
      vec[16]  = hashToFloat(ua.split("").reverse().join(""));

      // Indices 17–31 remain 0 (reserved)
      return vec;
    }

    /** Entropy score: variance across the 32-dim vector ∈ [0, 1]. */
    entropyScore(vec) {
      const mean = vec.reduce((a, b) => a + b, 0) / vec.length;
      const variance = vec.reduce((a, b) => a + (b - mean) ** 2, 0) / vec.length;
      return clamp(variance * 10, 0, 1);
    }
  }


  // ══════════════════════════════════════════════════════════════════════════
  // HoneypotEngine
  // Manages the full decoy lifecycle: inject → monitor → report → destroy.
  // ══════════════════════════════════════════════════════════════════════════

  class HoneypotEngine {
    constructor(transport, options) {
      this._transport   = transport;
      this._options     = options;
      this._challenges  = new Map();   // challenge_id → {config, decoyEls, timer, triggered}
      this._styleInjected = false;
    }

    /**
     * Receive a challenge config from a /score response and set up decoys.
     *
     * @param {Object} challenge  Parsed challenge payload from the server.
     * @param {string} sessionToken  Active session token for the trigger report.
     */
    applyChallenge(challenge, sessionToken) {
      if (!challenge || !challenge.challenge_id || !challenge.decoys) return;

      const { challenge_id } = challenge;

      // Deduplicate: ignore if we're already running this challenge
      if (this._challenges.has(challenge_id)) return;

      this._ensureStyle();
      const container = this._ensureContainer();
      const decoyEls  = [];

      for (const spec of challenge.decoys) {
        const el = this._renderDecoy(spec, challenge_id, sessionToken);
        if (el) {
          container.appendChild(el);
          decoyEls.push(el);
        }
      }

      // Auto-destroy when the challenge TTL expires
      const msUntilExpiry = Math.max(0, (challenge.expires_at * 1000) - Date.now());
      const timer = setTimeout(() => {
        this._destroyChallenge(challenge_id, "expired");
      }, msUntilExpiry);

      this._challenges.set(challenge_id, {
        config:    challenge,
        decoyEls,
        timer,
        triggered: false,
        sessionToken,
      });

      this._options.onDecoyInjected(challenge_id, challenge.decoys.length, challenge.arm);
    }

    /** Remove all decoys for all active challenges (e.g. on logout). */
    destroyAll() {
      for (const id of this._challenges.keys()) {
        this._destroyChallenge(id, "cleanup");
      }
    }

    // ── Private ──────────────────────────────────────────────────────────────

    _renderDecoy(spec, challengeId, sessionToken) {
      const wrap = document.createElement("div");
      wrap.setAttribute("aria-hidden", "true");
      wrap.style.cssText = [
        "position:absolute",
        "left:-99999px",
        "top:-99999px",
        "width:0",
        "height:0",
        "overflow:hidden",
        "opacity:0",
        "visibility:hidden",
        "pointer-events:none",   // humans cannot accidentally click
        "z-index:-9999",
      ].join(";");

      let inner;

      switch (spec.kind) {
        case "input": {
          inner = document.createElement("input");
          inner.type         = spec.autocomplete.includes("password") ? "password" : "text";
          inner.name         = spec.name;
          inner.id           = DECOY_PREFIX + spec.decoy_id;
          inner.autocomplete = spec.autocomplete || "off";
          inner.tabIndex     = -1;
          // Bots that fill autocomplete="email" etc will write here
          const WATCHED = ["focus", "input", "change", "blur"];
          WATCHED.forEach((ev) =>
            inner.addEventListener(ev, () =>
              this._onDecoyInteraction(challengeId, spec, ev, sessionToken)
            )
          );
          break;
        }
        case "button": {
          inner = document.createElement("button");
          inner.type      = "button";
          inner.name      = spec.name;
          inner.id        = DECOY_PREFIX + spec.decoy_id;
          inner.tabIndex  = -1;
          inner.textContent = spec.label;
          inner.addEventListener("click", () =>
            this._onDecoyInteraction(challengeId, spec, "click", sessionToken)
          );
          break;
        }
        case "link": {
          inner = document.createElement("a");
          inner.href      = "#";
          inner.name      = spec.name;
          inner.id        = DECOY_PREFIX + spec.decoy_id;
          inner.tabIndex  = -1;
          inner.textContent = spec.label;
          inner.addEventListener("click", (e) => {
            e.preventDefault();
            this._onDecoyInteraction(challengeId, spec, "click", sessionToken);
          });
          break;
        }
        case "checkbox": {
          inner = document.createElement("input");
          inner.type     = "checkbox";
          inner.name     = spec.name;
          inner.id       = DECOY_PREFIX + spec.decoy_id;
          inner.tabIndex = -1;
          inner.addEventListener("change", () =>
            this._onDecoyInteraction(challengeId, spec, "change", sessionToken)
          );
          break;
        }
        default:
          return null;
      }

      if (inner) {
        const lbl = document.createElement("label");
        lbl.htmlFor        = DECOY_PREFIX + spec.decoy_id;
        lbl.textContent    = spec.label;
        lbl.style.cssText  = "position:absolute;left:-99999px;opacity:0";
        wrap.appendChild(lbl);
        wrap.appendChild(inner);
      }

      return wrap;
    }

    _onDecoyInteraction(challengeId, spec, eventType, sessionToken) {
      const entry = this._challenges.get(challengeId);
      if (!entry || entry.triggered) return;   // fire only once per challenge

      entry.triggered = true;

      this._options.onDecoyTriggered(challengeId, spec.decoy_id, spec.kind, eventType);

      // Report to backend
      this._transport.post("/honeypot/trigger", {
        challenge_id:   challengeId,
        arm:            entry.config.arm,
        expires_at:     entry.config.expires_at,
        signature:      entry.config.signature,
        decoy_ids:      entry.config.decoys.map((d) => d.decoy_id),
        triggered_decoy: spec.decoy_id,
        trigger_event:  eventType,
        trigger_kind:   spec.kind,
        session_token:  sessionToken,
      }).catch(noop);  // fire-and-forget; never throws into user code

      // Self-destruct immediately after trigger
      this._destroyChallenge(challengeId, "triggered");
    }

    _destroyChallenge(challengeId, reason) {
      const entry = this._challenges.get(challengeId);
      if (!entry) return;

      clearTimeout(entry.timer);
      for (const el of entry.decoyEls) {
        try { el.parentNode && el.parentNode.removeChild(el); } catch {}
      }
      this._challenges.delete(challengeId);
      this._options.onDecoyDestroyed(challengeId, reason);
    }

    _ensureContainer() {
      let c = document.getElementById(DECOY_CONTAINER_ID);
      if (!c) {
        c = document.createElement("div");
        c.id = DECOY_CONTAINER_ID;
        c.setAttribute("aria-hidden", "true");
        c.setAttribute("role", "presentation");
        document.body.appendChild(c);
      }
      return c;
    }

    _ensureStyle() {
      if (this._styleInjected || document.getElementById(DECOY_STYLE_ID)) return;
      // Belt-and-suspenders CSS: even if someone inspects the DOM the decoys
      // remain invisible.  The id= selector is high-specificity on purpose.
      const s = document.createElement("style");
      s.id = DECOY_STYLE_ID;
      s.textContent = `
        #${DECOY_CONTAINER_ID},
        #${DECOY_CONTAINER_ID} * {
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
      `;
      (document.head || document.documentElement).appendChild(s);
      this._styleInjected = true;
    }
  }


  // ══════════════════════════════════════════════════════════════════════════
  // Transport
  // Thin fetch wrapper with retry and offline queue.
  // ══════════════════════════════════════════════════════════════════════════

  class Transport {
    constructor(endpoint, apiKey) {
      this._base   = endpoint.replace(/\/$/, "");
      this._apiKey = apiKey;
      this._queue  = [];      // offline queue
      this._online = true;

      window.addEventListener("online",  () => { this._online = true;  this._drainQueue(); });
      window.addEventListener("offline", () => { this._online = false; });
    }

    async post(path, body, retries = 2) {
      if (!this._online) {
        this._queue.push({ path, body });
        return null;
      }
      let lastErr;
      for (let attempt = 0; attempt <= retries; attempt++) {
        try {
          const res = await fetch(this._base + path, {
            method:  "POST",
            headers: {
              "Content-Type": "application/json",
              "X-API-Key":    this._apiKey,
              "X-EP-Version": SDK_VERSION,
            },
            body: JSON.stringify(body),
            keepalive: true,   // survives page unload for trigger reports
          });
          if (!res.ok) {
            const text = await res.text().catch(() => "");
            throw new Error(`HTTP ${res.status}: ${text}`);
          }
          return await res.json();
        } catch (err) {
          lastErr = err;
          if (attempt < retries) await this._sleep(200 * 2 ** attempt);
        }
      }
      throw lastErr;
    }

    _drainQueue() {
      while (this._queue.length > 0) {
        const { path, body } = this._queue.shift();
        this.post(path, body, 1).catch(noop);
      }
    }

    _sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
  }


  // ══════════════════════════════════════════════════════════════════════════
  // EntropySDK  — public surface
  // ══════════════════════════════════════════════════════════════════════════

  class EntropySDK {
    /**
     * @param {Object} opts
     * @param {string}   opts.apiKey           X-API-Key for the Entropy Prime gateway.
     * @param {string}   opts.endpoint         Base URL of the Entropy Prime API.
     * @param {string}   [opts.userId]         Pre-authenticated user ID (for heartbeat).
     * @param {string}   [opts.sessionToken]   Pre-existing session token (e.g. from SSR).
     * @param {Function} [opts.onScore]        Called with the full /score result.
     * @param {Function} [opts.onForceLogout]  Called when the watchdog issues FORCE_LOGOUT.
     * @param {Function} [opts.onDecoyInjected] Called when decoys are injected.
     * @param {Function} [opts.onDecoyTriggered] Called when a bot triggers a decoy.
     * @param {boolean}  [opts.debug]          Log internal state to console.
     */
    constructor(opts = {}) {
      if (!opts.apiKey)    throw new Error("[EntropySDK] apiKey is required");
      if (!opts.endpoint)  throw new Error("[EntropySDK] endpoint is required");

      this._opts = {
        onScore:          opts.onScore          || noop,
        onForceLogout:    opts.onForceLogout    || noop,
        onDecoyInjected:  opts.onDecoyInjected  || noop,
        onDecoyTriggered: opts.onDecoyTriggered || noop,
        debug:            opts.debug            || false,
      };

      this._sessionToken = opts.sessionToken || null;
      this._userId       = opts.userId       || null;
      this._running      = false;
      this._scoreTimer   = null;
      this._hbTimer      = null;

      this._transport  = new Transport(opts.endpoint, opts.apiKey);
      this._collector  = new BiometricCollector();
      this._honeypot   = new HoneypotEngine(this._transport, {
        onDecoyInjected:  (...a) => { this._log("Decoys injected", ...a); this._opts.onDecoyInjected(...a); },
        onDecoyTriggered: (...a) => { this._log("⚠ Decoy triggered", ...a); this._opts.onDecoyTriggered(...a); },
        onDecoyDestroyed: (...a) => { this._log("Decoys destroyed", ...a); },
      });
    }

    /**
     * Start the SDK: begin collecting biometrics, call /score, set up timers.
     * Safe to call multiple times — subsequent calls are no-ops.
     */
    init() {
      if (this._running) return this;
      this._running = true;

      this._log("EntropySDK v%s initialising", SDK_VERSION);
      this._collector.start();

      // Stagger the first /score call slightly to let the page settle
      setTimeout(() => this._doScore(), 800);

      this._scoreTimer = setInterval(() => this._doScore(), SCORE_INTERVAL_MS);

      return this;
    }

    /**
     * Update the session context (call after login / registration).
     *
     * @param {string} sessionToken
     * @param {string} userId
     */
    setSession(sessionToken, userId) {
      this._sessionToken = sessionToken;
      this._userId       = userId;
      this._log("Session set: user=%s", userId);

      // Start heartbeat now that we have a session
      this._startHeartbeat();
      return this;
    }

    /**
     * Clear the local session and stop the heartbeat.
     * Does NOT call /auth/logout — callers handle that separately.
     */
    clearSession() {
      this._sessionToken = null;
      this._userId       = null;
      this._stopHeartbeat();
      this._honeypot.destroyAll();
      this._log("Session cleared");
      return this;
    }

    /** Stop all SDK activity and clean up DOM. */
    destroy() {
      this._running = false;
      clearInterval(this._scoreTimer);
      this._stopHeartbeat();
      this._collector.stop();
      this._honeypot.destroyAll();
      this._log("SDK destroyed");
    }

    // ── Private: scoring ─────────────────────────────────────────────────────

    async _doScore() {
      const vec     = this._collector.snapshot();
      const theta   = vec[14];    // time-on-page as θ proxy
      const h_exp   = this._collector.entropyScore(vec);

      let result;
      try {
        result = await this._transport.post("/score", {
          theta,
          h_exp,
          server_load:   0.5,           // SDK doesn't know server load; default
          user_agent:    navigator.userAgent,
          latent_vector: vec,
        });
      } catch (err) {
        this._log("Score failed: %s", err.message);
        return;
      }

      this._log("Score result: shadow=%s preset=%s", result.shadow_mode, result.action_label);
      this._opts.onScore(result);

      // Apply challenge if present (shadow mode only)
      if (result.challenge && this._sessionToken) {
        this._honeypot.applyChallenge(result.challenge, this._sessionToken);
      }

      // If shadow mode → report MAB arm after a brief observation window
      if (result.shadow_mode && typeof result.mab_arm === "number") {
        this._scheduleMabReward(result.mab_arm);
      }
    }

    // ── Private: heartbeat ───────────────────────────────────────────────────

    _startHeartbeat() {
      this._stopHeartbeat();
      this._hbTimer = setInterval(() => this._doHeartbeat(), HEARTBEAT_MS);
    }

    _stopHeartbeat() {
      clearInterval(this._hbTimer);
      this._hbTimer = null;
    }

    async _doHeartbeat() {
      if (!this._sessionToken || !this._userId) return;

      const vec = this._collector.snapshot();

      let result;
      try {
        result = await this._transport.post("/session/verify", {
          session_token: this._sessionToken,
          user_id:       this._userId,
          latent_vector: vec,
          e_rec:         this._collector.entropyScore(vec),
        });
      } catch (err) {
        this._log("Heartbeat failed: %s", err.message);
        return;
      }

      this._log("Heartbeat: action=%s trust=%.3f", result.action, result.trust_score);

      if (result.session_invalidated || result.action === "FORCE_LOGOUT") {
        this._log("⚠ FORCE_LOGOUT received — clearing session");
        this.clearSession();
        this._opts.onForceLogout(result);
      }
    }

    // ── Private: MAB reward ──────────────────────────────────────────────────

    _scheduleMabReward(arm) {
      // Give the bot 8 s to interact (or not) with decoys, then report.
      // In a real deployment this would be driven by the /honeypot/trigger
      // callback that the backend sends after it validates the trigger event.
      // Here we send a neutral reward immediately as a fallback if no trigger
      // fires — the backend /honeypot/reward route will override if triggered.
      setTimeout(() => {
        this._transport.post("/honeypot/reward", { arm, reward: 0 }).catch(noop);
      }, 8_000);
    }

    // ── Private: logging ─────────────────────────────────────────────────────

    _log(...args) {
      if (this._opts.debug) {
        console.debug("[EntropySDK]", ...args);
      }
    }
  }


  // ── Expose ─────────────────────────────────────────────────────────────────

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { EntropySDK };                   // CommonJS / Node test env
  } else {
    global.EntropySDK = EntropySDK;                    // Browser global
  }

})(typeof globalThis !== "undefined" ? globalThis : this);