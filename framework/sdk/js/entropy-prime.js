/**
 * Entropy Prime — JavaScript SDK (browser)
 * ========================================
 * Drop-in client for the Entropy Prime behavioral security framework. Captures
 * lightweight behavioral signals in the browser, scores them through the
 * framework API, and surfaces the humanity score + session token to your app.
 *
 * Two integration tiers:
 *   1. Lightweight (this file, zero deps): a small keystroke/pointer collector
 *      computes a humanity *proxy* from timing variance. Good for demos and
 *      simple sites.
 *   2. Production: plug in the full TensorFlow.js engine from
 *      src/services/biometrics.js via `setEngine()` for CNN-based theta and a
 *      real 32-dim latent vector. The SDK calls the same API either way.
 *
 * Usage (CDN / <script type="module">):
 *
 *   import { EntropyPrime } from './entropy-prime.js'
 *   const ep = new EntropyPrime({
 *     apiUrl: 'https://api.example.com',
 *     onScore:  (score, label) => console.log(score, label),
 *     onSession:(token)        => (form.querySelector('#ep_token').value = token),
 *   })
 *   ep.attach(document.querySelector('#login-form'))
 *
 * Raw keystrokes / mouse coordinates never leave the browser — only the derived
 * humanity score and (with the production engine) a latent vector are sent.
 */

const LATENT_DIM = 32;

// ── Lightweight behavioral collector (humanity proxy) ────────────────────────
class BehavioralCollector {
  constructor() {
    this._dwell = [];
    this._flight = [];
    this._lastDown = null;
    this._lastUp = null;
    this._down = {};
    this._speeds = [];
    this._lastPt = null;
    this._bound = false;
  }

  attach(target = document) {
    if (this._bound) return;
    this._onDown = (e) => {
      const t = performance.now();
      this._down[e.code] = t;
      if (this._lastUp != null) this._flight.push(Math.max(0, t - this._lastUp));
      this._lastDown = t;
    };
    this._onUp = (e) => {
      const t = performance.now();
      const d = this._down[e.code];
      if (d != null) this._dwell.push(t - d);
      this._lastUp = t;
      if (this._dwell.length > 200) this._dwell.shift();
      if (this._flight.length > 200) this._flight.shift();
    };
    this._onMove = (e) => {
      const t = performance.now();
      if (this._lastPt) {
        const dt = (t - this._lastPt.t) / 1000 || 0.001;
        const dx = e.clientX - this._lastPt.x;
        const dy = e.clientY - this._lastPt.y;
        this._speeds.push(Math.sqrt(dx * dx + dy * dy) / dt);
        if (this._speeds.length > 300) this._speeds.shift();
      }
      this._lastPt = { x: e.clientX, y: e.clientY, t };
    };
    target.addEventListener('keydown', this._onDown);
    target.addEventListener('keyup', this._onUp);
    target.addEventListener('mousemove', this._onMove);
    this._target = target;
    this._bound = true;
  }

  detach() {
    if (!this._bound) return;
    this._target.removeEventListener('keydown', this._onDown);
    this._target.removeEventListener('keyup', this._onUp);
    this._target.removeEventListener('mousemove', this._onMove);
    this._bound = false;
  }

  /** Coefficient of variation → humanity proxy in [0,1]. Bots ~0 (scripted). */
  _cv(arr) {
    if (arr.length < 3) return 0.0;
    const mean = arr.reduce((s, v) => s + v, 0) / arr.length;
    if (mean <= 0) return 0.0;
    const variance = arr.reduce((s, v) => s + (v - mean) ** 2, 0) / arr.length;
    return Math.sqrt(variance) / mean;
  }

  humanity() {
    const cv = (this._cv(this._dwell) + this._cv(this._flight) + this._cv(this._speeds)) / 3;
    return Math.max(0, Math.min(1, cv / 0.4)); // ~0.4 CV ≈ confidently human
  }

  /** Deterministic latent proxy from aggregate stats (production: use tfjs engine). */
  latent() {
    const avg = (a) => (a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0);
    const seed = avg(this._dwell) + avg(this._flight) + avg(this._speeds);
    const v = new Array(LATENT_DIM);
    for (let i = 0; i < LATENT_DIM; i++) {
      v[i] = Math.tanh(Math.sin((i + 1) * 0.37 + seed * 0.001));
    }
    return v;
  }
}

// ── SDK ──────────────────────────────────────────────────────────────────────
export class EntropyPrime {
  /**
   * @param {object}   cfg
   * @param {string}   cfg.apiUrl      Framework base URL.
   * @param {string}  [cfg.prefix]     API version prefix (default '/v1').
   * @param {number}  [cfg.threshold]  Human/bot boundary (default 0.5).
   * @param {function}[cfg.onScore]    (score, label) => void
   * @param {function}[cfg.onSession]  (token) => void
   * @param {function}[cfg.onError]    (err) => void
   */
  constructor(cfg = {}) {
    this.apiUrl = (cfg.apiUrl || 'http://localhost:8000').replace(/\/$/, '');
    this.prefix = cfg.prefix !== undefined ? cfg.prefix : '/v1';
    this.threshold = cfg.threshold ?? 0.5;
    this.onScore = cfg.onScore;
    this.onSession = cfg.onSession;
    this.onError = cfg.onError;

    this.theta = null;
    this.sessionToken = null;
    this._collector = new BehavioralCollector();
    this._engine = null; // optional production tfjs engine
  }

  /** Plug in the full tfjs engine (src/services/biometrics.js EntropyPrimeClient). */
  setEngine(engine) { this._engine = engine; }

  attach(target = document) { this._collector.attach(target); return this; }
  detach() { this._collector.detach(); }

  _url(path) { return this.apiUrl + (this.prefix ? this.prefix : '') + path; }

  async _post(path, body, auth = false) {
    const headers = { 'Content-Type': 'application/json' };
    if (auth && this.sessionToken) headers['X-Session-Token'] = this.sessionToken;
    const res = await fetch(this._url(path), {
      method: 'POST', headers, body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `API error ${res.status}`);
    return data;
  }

  /** Compute current signals (engine if present, else proxy). */
  async _signals() {
    if (this._engine && typeof this._engine.evaluate === 'function') {
      const { theta, hExp } = await this._engine.evaluate();
      const latent = await this._engine.getLatentVector();
      return { theta, hExp: hExp ?? 0.5, latent };
    }
    return { theta: this._collector.humanity(), hExp: 0.5, latent: this._collector.latent() };
  }

  /** Force a score now → POST /score. Returns the pipeline result. */
  async flush() {
    try {
      const { theta, hExp, latent } = await this._signals();
      this.theta = theta;
      const result = await this._post('/score', {
        theta, h_exp: hExp, server_load: 0.5,
        user_agent: navigator.userAgent, latent_vector: latent,
      });
      this.sessionToken = result.session_token;
      const label = theta >= this.threshold ? 'human' : 'bot';
      this.onScore && this.onScore(theta, label);
      this.onSession && this.onSession(result.session_token);
      return result;
    } catch (err) {
      this.onError ? this.onError(err) : console.error('[EntropyPrime]', err);
      throw err;
    }
  }

  // ── REST convenience ───────────────────────────────────────────────────────
  async register(email, password) {
    const r = await this._post('/auth/register', { email, plain_password: password });
    this.sessionToken = r.session_token; return r;
  }
  async login(email, password) {
    const r = await this._post('/auth/login', { email, plain_password: password });
    this.sessionToken = r.session_token; return r;
  }
  async verify(userId, latentVector, eRec, extra = {}) {
    return this._post('/session/verify', {
      session_token: this.sessionToken || '', user_id: userId,
      latent_vector: latentVector, e_rec: eRec,
      onboarding_state: 'collecting', ...extra,
    });
  }
  async trust(userId, transactionRisk = 0.5, extra = {}) {
    return this._post('/session/trust', {
      session_token: this.sessionToken || '', user_id: userId,
      transaction_risk: transactionRisk, ...extra,
    });
  }
}

export default EntropyPrime;
