/**
 * Entropy Prime — Biometrics Engine (Browser-side)
 * All raw signals are processed here. Only θ and latent vectors leave the browser.
 */
import * as tf from '@tensorflow/tfjs'

<<<<<<< Updated upstream
const CNN_SEQ_LEN  = 50
const CNN_FEATURES = 4   // dwell, flight, speed, jitter
const LATENT_DIM   = 32
const EREC_THRESH  = 0.18
=======
// ── Constants ──────────────────────────────────────────────────────────────
const CNN_SEQ_LEN   = 50
const CNN_FEATURES  = 8   // expanded: dwell, flight, speed, jitter, accel, rhythm, pressure_proxy, pause
const LATENT_DIM    = 32
const EREC_THRESH   = 0.25 // increased from 0.20 for even less sensitivity
const PROFILE_WIN   = 200 // rolling window for per-user profile update
const DRIFT_ALPHA   = 0.01 // reduced from 0.02 for much slower, stable adaptation
const FEAT_K        = 6   // top-K features selected per user
const ANOMALY_BUFFER = 5  // increased from 3: require 5 consecutive anomalies
const EREC_ALPHA    = 0.10 // reduced from 0.15 for stronger smoothing of spikes
>>>>>>> Stashed changes

// ─── Zipf Entropy ─────────────────────────────────────────────────────────────
export function computeExpectationEntropy(password) {
  if (!password) return 0
  const freq = {}
  for (const ch of password) freq[ch] = (freq[ch] || 0) + 1
  const counts = Object.values(freq).sort((a, b) => b - a)
  const N = password.length
  const k = counts.length
  let H_k = 0
  for (let i = 1; i <= k; i++) H_k += 1 / i
  let H_obs = 0
  for (const c of counts) { const p = c / N; H_obs -= p * Math.log2(p) }
  const maxH = Math.log2(Math.min(k, 94))
  return maxH > 0 ? Math.min(H_obs / maxH, 1.0) : 0
}

<<<<<<< Updated upstream
// ─── Keyboard Collector ───────────────────────────────────────────────────────
=======
// ── Feature Names (8 dimensions) ─────────────────────────────────────────────
export const FEATURE_NAMES = [
  'dwell_norm',      // key press duration
  'flight_norm',     // inter-key gap
  'speed_norm',      // pointer speed
  'jitter_norm',     // pointer micro-tremor
  'accel_norm',      // pointer acceleration magnitude
  'rhythm_norm',     // keystroke rhythm consistency (CV of dwell)
  'pause_norm',      // long pauses between bursts
  'bigram_norm',     // common bigram dwell ratio
]

// ── Per-User Feature Selector ─────────────────────────────────────────────────
/**
 * Tracks per-user feature variance and selects the K most discriminative
 * features based on coefficient of variation (high CV = high signal).
 * Updated online using an exponential moving average.
 */
export class UserFeatureSelector {
  constructor(k = FEAT_K) {
    this.k = k
    this.means   = new Float32Array(CNN_FEATURES).fill(0.5)
    this.m2s     = new Float32Array(CNN_FEATURES).fill(0.1)  // variance accumulator
    this.n       = 0
    this._selected = Array.from({ length: CNN_FEATURES }, (_, i) => i) // initial: all
  }

  /**
   * Welford online update of mean + variance per feature
   */
  update(featureVec) {
    this.n++
    for (let i = 0; i < CNN_FEATURES; i++) {
      const delta  = featureVec[i] - this.means[i]
      this.means[i] += delta / this.n
      const delta2 = featureVec[i] - this.means[i]
      this.m2s[i]  += delta * delta2
    }
    // Recompute selected features every 20 observations
    if (this.n % 20 === 0) this._reselect()
  }

  _reselect() {
    const cvs = Array.from({ length: CNN_FEATURES }, (_, i) => {
      const variance = this.n > 1 ? this.m2s[i] / (this.n - 1) : 0
      const std = Math.sqrt(variance)
      return this.means[i] > 0 ? std / this.means[i] : 0 // CV
    })
    // Top-K by CV
    this._selected = cvs
      .map((cv, i) => ({ cv, i }))
      .sort((a, b) => b.cv - a.cv)
      .slice(0, this.k)
      .map(x => x.i)
      .sort((a, b) => a - b) // keep original order
  }

  get selectedIndices() { return this._selected }

  /**
   * Return only the selected feature subset from a full vector
   */
  project(featureVec) {
    return this._selected.map(i => featureVec[i])
  }

  toJSON() {
    return {
      means: Array.from(this.means),
      m2s:   Array.from(this.m2s),
      n:     this.n,
      selected: this._selected,
    }
  }

  static fromJSON(obj) {
    if (!obj) return new UserFeatureSelector()
    const sel = new UserFeatureSelector()
    sel.means    = new Float32Array(obj.means)
    sel.m2s      = new Float32Array(obj.m2s)
    sel.n        = obj.n
    sel._selected = obj.selected
    return sel
  }
}

// ── Behavioral Profile ────────────────────────────────────────────────────────
/**
 * Per-user EMA profile over feature vectors.
 * Detects behavioral drift using Mahalanobis-lite distance.
 */
export class UserBehavioralProfile {
  constructor() {
    this.emaProfile  = null           // Float32Array of CNN_FEATURES
    this.emaVariance = null           // Float32Array — rolling variance
    this.sampleCount = 0
    this.driftHistory = []            // last 100 drift scores
    this.lastDrift    = 0
    this.driftSmooth  = 0             // EMA-smoothed drift for stability
  }

  /**
   * Update EMA profile with new feature vector.
   * Returns drift score relative to current profile.
   */
  update(featureVec) {
    const vec = Float32Array.from(featureVec)

    if (!this.emaProfile) {
      this.emaProfile  = new Float32Array(vec)
      this.emaVariance = new Float32Array(CNN_FEATURES).fill(0.08) // increased from 0.05 for even more stability
      this.sampleCount = 1
      return 0
    }

    this.sampleCount++
    const alpha = DRIFT_ALPHA

    // Compute per-feature deviation before updating profile
    let drift = 0
    for (let i = 0; i < CNN_FEATURES; i++) {
      const diff = vec[i] - this.emaProfile[i]
      const variance = Math.max(this.emaVariance[i], 0.01) // enforce minimum variance
      const std  = Math.sqrt(variance) + 1e-8
      drift += (diff / std) ** 2
      // EMA update with reduced alpha for stability
      this.emaProfile[i]  = (1 - alpha) * this.emaProfile[i]  + alpha * vec[i]
      this.emaVariance[i] = (1 - alpha) * this.emaVariance[i] + alpha * diff * diff
    }
    drift = Math.sqrt(drift / CNN_FEATURES) // normalized Mahalanobis-lite

    // Smooth drift with EMA to suppress temporary spikes (much stronger smoothing)
    this.driftSmooth = this.driftSmooth === 0 ? drift : 0.2 * this.driftSmooth + 0.8 * drift
    this.lastDrift = this.driftSmooth
    this.driftHistory.push(this.driftSmooth)
    if (this.driftHistory.length > 100) this.driftHistory.shift()

    console.log(`[BehavioralProfile] Updated drift: ${drift.toFixed(3)}, sampleCount: ${this.sampleCount}`)
    return drift
  }

  /**
   * Baseline drift threshold: mean + 2σ of observed drift history.
   * Adapts per-user over time.
   */
  get adaptiveThreshold() {
    if (this.driftHistory.length < 30) return 3.5 // extended warm-up: very permissive
    const mean = this.driftHistory.reduce((s, v) => s + v, 0) / this.driftHistory.length
    const std  = Math.sqrt(
      this.driftHistory.reduce((s, v) => s + (v - mean) ** 2, 0) / this.driftHistory.length
    )
    // increased from 3*std to 4*std for much more tolerance to natural variation
    return Math.max(1.5, mean + 4 * std)
  }

  get isDrifting() {
    // increased from 50 to 100 samples for longer calibration
    return this.sampleCount > 100 && this.lastDrift > this.adaptiveThreshold
  }

  toJSON() {
    return {
      emaProfile:   this.emaProfile ? Array.from(this.emaProfile) : null,
      emaVariance:  this.emaVariance ? Array.from(this.emaVariance) : null,
      sampleCount:  this.sampleCount,
      driftHistory: this.driftHistory,
      lastDrift:    this.lastDrift,
    }
  }

  static fromJSON(obj) {
    const p = new UserBehavioralProfile()
    if (!obj) return p
    if (obj.emaProfile)  p.emaProfile  = new Float32Array(obj.emaProfile)
    if (obj.emaVariance) p.emaVariance = new Float32Array(obj.emaVariance)
    p.sampleCount  = obj.sampleCount  || 0
    p.driftHistory = obj.driftHistory || []
    p.lastDrift    = obj.lastDrift    || 0
    return p
  }
}

// ── Keyboard Collector (expanded) ─────────────────────────────────────────────
>>>>>>> Stashed changes
export class KeyboardCollector {
  constructor() {
    this._events = []
    this._keyDownTs = {}
    this._lastKeyUp = null
  }
  start(target = document) {
    this._onDown = e => { this._keyDownTs[e.code] = performance.now() }
    this._onUp   = e => {
      const now  = performance.now()
      const down = this._keyDownTs[e.code]
      if (down === undefined) return
      const dwell  = now - down
      const flight = this._lastKeyUp !== null ? down - this._lastKeyUp : 0
      this._events.push({ dwell, flight, ts: now })
      if (this._events.length > 300) this._events.shift()
      this._lastKeyUp = now
    }
    target.addEventListener('keydown', this._onDown)
    target.addEventListener('keyup',   this._onUp)
  }
  stop(target = document) {
    target.removeEventListener('keydown', this._onDown)
    target.removeEventListener('keyup',   this._onUp)
  }
  getWindow(n = CNN_SEQ_LEN) { return this._events.slice(-n) }
  getStats() {
    if (!this._events.length) return { avgDwell: 0, avgFlight: 0, count: 0 }
    const avg = arr => arr.reduce((s, v) => s + v, 0) / arr.length
    return {
      avgDwell:  avg(this._events.map(e => e.dwell)),
      avgFlight: avg(this._events.map(e => e.flight)),
      count:     this._events.length,
    }
  }
  clear() { this._events = [] }
}

// ─── Pointer Collector ────────────────────────────────────────────────────────
export class PointerCollector {
  constructor() {
    this._samples = []
    this._prev    = null
    this._prevV   = null
  }
  start(target = document) {
    this._onMove = e => this._handle(e.clientX, e.clientY, performance.now())
    target.addEventListener('mousemove', this._onMove)
    target.addEventListener('touchmove', e => {
      const t = e.touches[0]
      this._handle(t.clientX, t.clientY, performance.now())
    }, { passive: true })
  }
  stop(target = document) {
    target.removeEventListener('mousemove', this._onMove)
  }
  _handle(x, y, now) {
    if (!this._prev) { this._prev = { x, y, t: now }; return }
    const dt = (now - this._prev.t) / 1000 || 0.001
    const vx = (x - this._prev.x) / dt
    const vy = (y - this._prev.y) / dt
    let ax = 0, ay = 0
    if (this._prevV) { ax = (vx - this._prevV.vx) / dt; ay = (vy - this._prevV.vy) / dt }
    const jitter = this._prevV
      ? Math.sqrt((vx - this._prevV.vx) ** 2 + (vy - this._prevV.vy) ** 2) : 0
    this._samples.push({ vx, vy, ax, ay, jitter, speed: Math.sqrt(vx*vx+vy*vy), ts: now })
    if (this._samples.length > 500) this._samples.shift()
    this._prevV = { vx, vy }
    this._prev  = { x, y, t: now }
  }
  getWindow(n = CNN_SEQ_LEN) { return this._samples.slice(-n) }
  getStats() {
    if (!this._samples.length) return { avgSpeed: 0, avgJitter: 0, count: 0 }
    const avg = arr => arr.reduce((s, v) => s + v, 0) / arr.length
    return {
      avgSpeed:  avg(this._samples.map(s => s.speed)),
      avgJitter: avg(this._samples.map(s => s.jitter)),
      count:     this._samples.length,
    }
  }
}

// ─── 1D-CNN ───────────────────────────────────────────────────────────────────
export function buildHumanityScoreCNN() {
  const input = tf.input({ shape: [CNN_SEQ_LEN, CNN_FEATURES] })
  let x = tf.layers.conv1d({ filters: 32, kernelSize: 5, padding: 'same', activation: 'relu' }).apply(input)
  x = tf.layers.batchNormalization().apply(x)
  x = tf.layers.conv1d({ filters: 64, kernelSize: 3, padding: 'same', activation: 'relu' }).apply(x)
  x = tf.layers.batchNormalization().apply(x)
  x = tf.layers.globalMaxPooling1d().apply(x)
  x = tf.layers.dense({ units: 32, activation: 'relu' }).apply(x)
  x = tf.layers.dropout({ rate: 0.3 }).apply(x)
  const output = tf.layers.dense({ units: 1, activation: 'sigmoid' }).apply(x)
  const model = tf.model({ inputs: input, outputs: output })
  model.compile({ optimizer: tf.train.adam(1e-3), loss: 'binaryCrossentropy' })
  return model
}

export function buildCNNInput(keyEvents, pointerEvents) {
  const seq  = CNN_SEQ_LEN
  const data = new Float32Array(seq * CNN_FEATURES)
  for (let i = 0; i < seq; i++) {
    const ke = keyEvents[i]   || { dwell: 0, flight: 0 }
    const pe = pointerEvents[i] || { speed: 0, jitter: 0 }
    data[i * CNN_FEATURES + 0] = Math.min(ke.dwell  / 300, 1)
    data[i * CNN_FEATURES + 1] = Math.min(ke.flight / 500, 1)
    data[i * CNN_FEATURES + 2] = Math.min(pe.speed  / 2000, 1)
    data[i * CNN_FEATURES + 3] = Math.min(pe.jitter / 100, 1)
  }
  return tf.tensor3d(data, [1, seq, CNN_FEATURES])
}

// ─── Autoencoder ──────────────────────────────────────────────────────────────
export function buildAutoencoder(inputDim = CNN_SEQ_LEN * CNN_FEATURES) {
  const encInput = tf.input({ shape: [inputDim] })
  let enc = tf.layers.dense({ units: 128, activation: 'relu' }).apply(encInput)
  enc = tf.layers.dense({ units: 64, activation: 'relu' }).apply(enc)
  enc = tf.layers.dense({ units: LATENT_DIM, activation: 'linear', name: 'latent' }).apply(enc)
  let dec = tf.layers.dense({ units: 64,       activation: 'relu' }).apply(enc)
  dec = tf.layers.dense({ units: 128,      activation: 'relu' }).apply(dec)
  dec = tf.layers.dense({ units: inputDim, activation: 'sigmoid' }).apply(dec)
  const autoencoder = tf.model({ inputs: encInput, outputs: dec })
  autoencoder.compile({ optimizer: tf.train.adam(1e-3), loss: 'meanSquaredError' })
  const encoder = tf.model({ inputs: encInput, outputs: enc })
  return { autoencoder, encoder }
}

// ─── Session Watchdog ─────────────────────────────────────────────────────────
export class SessionWatchdog {
  constructor(autoencoder, encoder, onAnomaly) {
    this._ae       = autoencoder
    this._enc      = encoder
    this._baseline = null
    this._onAnomaly = onAnomaly
    this._timer    = null
    this.trustScore = 1.0
    this.lastERec   = 0
<<<<<<< Updated upstream
=======
    this.lastDrift  = 0
    this.eRecSmooth = 0              // EMA for e_rec stability
    this.anomalyCount = 0            // counter for consecutive anomalies
    this.lastAnomalyTime = 0         // timestamp of last anomaly
>>>>>>> Stashed changes
  }
  async anchorIdentity(vectors) {
    const latents = await Promise.all(
      vectors.map(v => this._enc.predict(tf.tensor2d([v], [1, v.length])).data())
    )
    const mean = new Float32Array(LATENT_DIM)
    for (const l of latents)
      for (let i = 0; i < LATENT_DIM; i++) mean[i] += l[i] / latents.length
    this._baseline = mean
    this._timer = setInterval(() => this._verify(), 30_000)
  }
  stop() { if (this._timer) clearInterval(this._timer) }
  async check(vector) { return this._verifyVector(vector) }
  async _verify() { /* called by timer — needs external vector feed */ }
  async _verifyVector(vector) {
    const t = tf.tensor2d([vector], [1, vector.length])
    const r = this._ae.predict(t)
    const eRecRaw = (await tf.losses.meanSquaredError(t.flatten(), r.flatten()).data())[0]
    t.dispose(); r.dispose()
<<<<<<< Updated upstream
    this.lastERec = eRec
    if (eRec > EREC_THRESH) {
      const strength = Math.min((eRec - EREC_THRESH) / EREC_THRESH, 1)
      this.trustScore = Math.max(0, this.trustScore - 0.15 * strength)
      this._onAnomaly({ eRec, trustScore: this.trustScore })
=======

    // Smooth e_rec with EMA to reduce spike sensitivity (stronger smoothing)
    this.eRecSmooth = this.eRecSmooth === 0 ? eRecRaw : 0.20 * this.eRecSmooth + 0.80 * eRecRaw
    this.lastERec = this.eRecSmooth
    this.lastDrift = behavioralProfile?.lastDrift ?? 0

    const now = Date.now()
    const timeSinceLastAnomaly = now - this.lastAnomalyTime

    // Much more tolerant threshold: only flag sustained, strong anomalies
    const baseThreshold = EREC_THRESH
    const isAnomaly = this.eRecSmooth > baseThreshold && (behavioralProfile?.isDrifting ?? false)

    if (isAnomaly) {
      this.anomalyCount++
      this.lastAnomalyTime = now

      // Only trigger callback if 5+ consecutive anomalies within 3 seconds
      if (this.anomalyCount >= ANOMALY_BUFFER && timeSinceLastAnomaly < 3000) {
        const strength = Math.min((this.eRecSmooth - baseThreshold) / Math.max(baseThreshold, 0.01), 1)
        // very slow trust decay: reduced from 0.04 to 0.02
        this.trustScore = Math.max(0, this.trustScore - 0.02 * Math.max(strength, 0.15))
        this._onAnomaly({ eRec: this.eRecSmooth, trustScore: this.trustScore, drift: this.lastDrift })
      }
>>>>>>> Stashed changes
    } else {
      // Reset anomaly counter on clean signal
      if (timeSinceLastAnomaly > 5000) {
        this.anomalyCount = 0
      }
      // restore trust more aggressively when session is clean
      this.trustScore = Math.min(1.0, this.trustScore + 0.02)
    }
    return { eRec: this.eRecSmooth, trustScore: this.trustScore }
  }
}

// ─── Main Client ──────────────────────────────────────────────────────────────
export class EntropyPrimeClient {
  constructor() {
    this.keyboard  = new KeyboardCollector()
    this.pointer   = new PointerCollector()
    this.cnn       = null
    this.watchdog  = null
    this.theta     = null
    this.hExp      = null
    this._ready    = false
    this._onUpdate = null
  }

  setUpdateCallback(fn) { this._onUpdate = fn }

  async init() {
    this.cnn = buildHumanityScoreCNN()
    const { autoencoder, encoder } = buildAutoencoder()
    this.watchdog = new SessionWatchdog(autoencoder, encoder, data => {
      this._onUpdate?.({ type: 'anomaly', ...data })
    })
    this.keyboard.start()
    this.pointer.start()
    this._ready = true
    // Live evaluation loop
    this._evalLoop = setInterval(() => this._liveEval(), 1500)
    this._onUpdate?.({ type: 'ready' })
  }

  async _liveEval() {
    if (!this._ready || !this.cnn) return
    try {
      const t = buildCNNInput(this.keyboard.getWindow(), this.pointer.getWindow())
      const s = this.cnn.predict(t)
      this.theta = (await s.data())[0]
      t.dispose(); s.dispose()
      this._onUpdate?.({ type: 'score', theta: this.theta })
    } catch {}
  }

  async evaluate(password = '') {
    const t    = buildCNNInput(this.keyboard.getWindow(), this.pointer.getWindow())
    const s    = this.cnn.predict(t)
    this.theta = (await s.data())[0]
    t.dispose(); s.dispose()
    this.hExp  = computeExpectationEntropy(password)
    return { theta: this.theta, hExp: this.hExp }
  }

  async getLatentVector() {
    const t = buildCNNInput(this.keyboard.getWindow(), this.pointer.getWindow())
    const flat = Array.from(t.dataSync())
    t.dispose()
    const enc = this.watchdog._enc
    if (!enc) return Array(32).fill(0)
    const lt = enc.predict(tf.tensor2d([flat], [1, flat.length]))
    const vec = Array.from(await lt.data())
    lt.dispose()
    return vec
  }

  getKeyboardStats() { return this.keyboard.getStats() }
  getPointerStats()  { return this.pointer.getStats() }

  destroy() {
    this.keyboard.stop()
    this.pointer.stop()
    if (this._evalLoop) clearInterval(this._evalLoop)
    if (this.watchdog) this.watchdog.stop()
  }
}
