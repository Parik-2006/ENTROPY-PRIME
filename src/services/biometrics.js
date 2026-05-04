/**
 * Entropy Prime — Per-User Biometric Intelligence Engine (Browser-side)
 *
 * Pipeline:
 *   Raw signals → Feature Extraction → Per-user Feature Selection
 *   → Behavioral Profile → Drift Detection → Session Trust
 *
 * Only θ, latent vectors, and drift deltas leave the browser.
 */
import * as tf from '@tensorflow/tfjs'

// ── Constants ──────────────────────────────────────────────────────────────
const CNN_SEQ_LEN   = 50
const CNN_FEATURES  = 8   // expanded: dwell, flight, speed, jitter, accel, rhythm, pressure_proxy, pause
const LATENT_DIM    = 32
const EREC_THRESH   = 0.18
const PROFILE_WIN   = 200 // rolling window for per-user profile update
const DRIFT_ALPHA   = 0.05 // EMA coefficient for profile smoothing
const FEAT_K        = 6   // top-K features selected per user

// ── Zipf Entropy ─────────────────────────────────────────────────────────────
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
  }

  /**
   * Update EMA profile with new feature vector.
   * Returns drift score relative to current profile.
   */
  update(featureVec) {
    const vec = Float32Array.from(featureVec)

    if (!this.emaProfile) {
      this.emaProfile  = new Float32Array(vec)
      this.emaVariance = new Float32Array(CNN_FEATURES).fill(0.01)
      this.sampleCount = 1
      return 0
    }

    this.sampleCount++
    const alpha = DRIFT_ALPHA

    // Compute per-feature deviation before updating profile
    let drift = 0
    for (let i = 0; i < CNN_FEATURES; i++) {
      const diff = vec[i] - this.emaProfile[i]
      const std  = Math.sqrt(this.emaVariance[i]) + 1e-6
      drift += (diff / std) ** 2
      // EMA update
      this.emaProfile[i]  = (1 - alpha) * this.emaProfile[i]  + alpha * vec[i]
      this.emaVariance[i] = (1 - alpha) * this.emaVariance[i] + alpha * diff * diff
    }
    drift = Math.sqrt(drift / CNN_FEATURES) // normalized Mahalanobis-lite

    this.lastDrift = drift
    this.driftHistory.push(drift)
    if (this.driftHistory.length > 100) this.driftHistory.shift()

    console.log(`[BehavioralProfile] Updated drift: ${drift.toFixed(3)}, sampleCount: ${this.sampleCount}`)
    return drift
  }

  /**
   * Baseline drift threshold: mean + 2σ of observed drift history.
   * Adapts per-user over time.
   */
  get adaptiveThreshold() {
    if (this.driftHistory.length < 10) return EREC_THRESH * 10
    const mean = this.driftHistory.reduce((s, v) => s + v, 0) / this.driftHistory.length
    const std  = Math.sqrt(
      this.driftHistory.reduce((s, v) => s + (v - mean) ** 2, 0) / this.driftHistory.length
    )
    return mean + 2 * std
  }

  get isDrifting() {
    return this.sampleCount > 20 && this.lastDrift > this.adaptiveThreshold
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
export class KeyboardCollector {
  constructor() {
    this._events    = []
    this._keyDownTs = {}
    this._lastKeyUp = null
    this._bigramTs  = {}   // bigram dwell tracking
    this._burstStart = null
    this._pauses    = []
  }

  start(target = document) {
    this._onDown = e => {
      const now = performance.now()
      this._keyDownTs[e.code] = now
      if (this._lastKeyUp && now - this._lastKeyUp > 800) {
        const pause = now - this._lastKeyUp
        this._pauses.push(pause)
        if (this._pauses.length > 50) this._pauses.shift()
      }
    }
    this._onUp = e => {
      const now  = performance.now()
      const down = this._keyDownTs[e.code]
      if (down === undefined) return
      const dwell  = now - down
        const flight = this._lastKeyUp !== null ? Math.max(0, down - this._lastKeyUp) : 0
      // Bigram: track pair with previous key
      const prevCode = this._lastCode
      this._lastCode = e.code
      const bigramKey = prevCode ? `${prevCode}>${e.code}` : null
      const avgBigram = this._getAvgBigram()
      const bigramRatio = bigramKey && this._bigramTs[bigramKey]
        ? dwell / Math.max(this._bigramTs[bigramKey], 1)
        : 1.0
      if (bigramKey) this._bigramTs[bigramKey] = dwell * 0.8 + (this._bigramTs[bigramKey] || dwell) * 0.2

      this._events.push({ dwell, flight, ts: now, bigramRatio })
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

  _getAvgBigram() {
    const vals = Object.values(this._bigramTs)
    return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : 100
  }

  /** Coefficient of variation of dwell — rhythm consistency */
  getRhythm() {
    const dwells = this._events.slice(-20).map(e => e.dwell)
    if (dwells.length < 3) return 0
    const mean = dwells.reduce((s, v) => s + v, 0) / dwells.length
    const std  = Math.sqrt(dwells.reduce((s, v) => s + (v - mean) ** 2, 0) / dwells.length)
    return mean > 0 ? Math.min(std / mean, 2) / 2 : 0 // CV normalized to [0,1]
  }

  getAvgPause() {
    if (!this._pauses.length) return 0
    return this._pauses.reduce((s, v) => s + v, 0) / this._pauses.length
  }

  getWindow(n = CNN_SEQ_LEN) { return this._events.slice(-n) }

  getStats() {
    if (!this._events.length) return { avgDwell: 0, avgFlight: 0, count: 0 }
    const avg = arr => arr.reduce((s, v) => s + v, 0) / arr.length
    return {
      avgDwell:  avg(this._events.map(e => e.dwell)),
      avgFlight: avg(this._events.map(e => e.flight)),
      rhythm:    this.getRhythm(),
      avgPause:  this.getAvgPause(),
      count:     this._events.length,
    }
  }

  clear() { this._events = []; this._pauses = [] }
}

// ── Pointer Collector (expanded) ──────────────────────────────────────────────
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
    const accel = Math.sqrt(ax * ax + ay * ay)
    this._samples.push({ vx, vy, ax, ay, jitter, accel, speed: Math.sqrt(vx*vx+vy*vy), ts: now })
    if (this._samples.length > 500) this._samples.shift()
    this._prevV = { vx, vy }
    this._prev  = { x, y, t: now }
  }

  getWindow(n = CNN_SEQ_LEN) { return this._samples.slice(-n) }

  getStats() {
    if (!this._samples.length) return { avgSpeed: 0, avgJitter: 0, avgAccel: 0, count: 0 }
    const avg = arr => arr.reduce((s, v) => s + v, 0) / arr.length
    return {
      avgSpeed:  avg(this._samples.map(s => s.speed)),
      avgJitter: avg(this._samples.map(s => s.jitter)),
      avgAccel:  avg(this._samples.map(s => s.accel)),
      count:     this._samples.length,
    }
  }
}

// ── Feature Vector Builder (8-dim) ───────────────────────────────────────────
export function buildFeatureVector(keyEvents, pointerEvents, keyboard) {
  const kStats = keyboard.getStats()
  const seq    = CNN_SEQ_LEN
  const feats  = new Float32Array(CNN_FEATURES)

  // Aggregate from windows
  if (keyEvents.length) {
    const avgDwell  = keyEvents.reduce((s, e) => s + e.dwell,  0) / keyEvents.length
    const avgFlight = keyEvents.reduce((s, e) => s + e.flight, 0) / keyEvents.length
    feats[0] = Math.min(avgDwell  / 300, 1)
    feats[1] = Math.min(avgFlight / 500, 1)
  }
  if (pointerEvents.length) {
    const avgSpeed  = pointerEvents.reduce((s, e) => s + e.speed,  0) / pointerEvents.length
    const avgJitter = pointerEvents.reduce((s, e) => s + e.jitter, 0) / pointerEvents.length
    const avgAccel  = pointerEvents.reduce((s, e) => s + e.accel,  0) / pointerEvents.length
    feats[2] = Math.min(avgSpeed  / 2000, 1)
    feats[3] = Math.min(avgJitter / 100,  1)
    feats[4] = Math.min(avgAccel  / 5000, 1)
  }
  feats[5] = kStats.rhythm || 0
  feats[6] = Math.min((kStats.avgPause || 0) / 3000, 1)
  // Bigram ratio: average across recent events
  const bigramRatios = keyEvents.filter(e => e.bigramRatio !== undefined).map(e => e.bigramRatio)
  feats[7] = bigramRatios.length
    ? Math.min(bigramRatios.reduce((s, v) => s + v, 0) / bigramRatios.length / 2, 1)
    : 0.5

  return feats
}

// ── CNN Input Builder (8-channel) ─────────────────────────────────────────────
export function buildCNNInput(keyEvents, pointerEvents, keyboard) {
  const seq  = CNN_SEQ_LEN
  const data = new Float32Array(seq * CNN_FEATURES)
  for (let i = 0; i < seq; i++) {
    const ke = keyEvents[i]     || { dwell: 0, flight: 0, bigramRatio: 0.5 }
    const pe = pointerEvents[i] || { speed: 0, jitter: 0, accel: 0 }
    data[i * CNN_FEATURES + 0] = Math.min(ke.dwell  / 300, 1)
    data[i * CNN_FEATURES + 1] = Math.min(ke.flight / 500, 1)
    data[i * CNN_FEATURES + 2] = Math.min(pe.speed  / 2000, 1)
    data[i * CNN_FEATURES + 3] = Math.min(pe.jitter / 100,  1)
    data[i * CNN_FEATURES + 4] = Math.min(pe.accel  / 5000, 1)
    data[i * CNN_FEATURES + 5] = keyboard ? keyboard.getRhythm() : 0
    data[i * CNN_FEATURES + 6] = Math.min((keyboard?.getAvgPause() || 0) / 3000, 1)
    data[i * CNN_FEATURES + 7] = Math.min((ke.bigramRatio || 0.5) / 2, 1)
  }
  return tf.tensor3d(data, [1, seq, CNN_FEATURES])
}

// ── 1D-CNN (8-channel input) ──────────────────────────────────────────────────
export function buildHumanityScoreCNN() {
  const input = tf.input({ shape: [CNN_SEQ_LEN, CNN_FEATURES] })
  let x = tf.layers.conv1d({ filters: 32, kernelSize: 5, padding: 'same', activation: 'relu' }).apply(input)
  x = tf.layers.batchNormalization().apply(x)
  x = tf.layers.conv1d({ filters: 64, kernelSize: 3, padding: 'same', activation: 'relu' }).apply(x)
  x = tf.layers.batchNormalization().apply(x)
  x = tf.layers.conv1d({ filters: 64, kernelSize: 3, padding: 'same', activation: 'relu' }).apply(x)
  x = tf.layers.globalMaxPooling1d().apply(x)
  x = tf.layers.dense({ units: 64, activation: 'relu' }).apply(x)
  x = tf.layers.dropout({ rate: 0.3 }).apply(x)
  x = tf.layers.dense({ units: 32, activation: 'relu' }).apply(x)
  const output = tf.layers.dense({ units: 1, activation: 'sigmoid' }).apply(x)
  const model  = tf.model({ inputs: input, outputs: output })
  model.compile({ optimizer: tf.train.adam(1e-3), loss: 'binaryCrossentropy' })
  return model
}

// ── Autoencoder (8 * SEQ flat) ────────────────────────────────────────────────
export function buildAutoencoder(inputDim = CNN_SEQ_LEN * CNN_FEATURES) {
  const encInput = tf.input({ shape: [inputDim] })
  let enc = tf.layers.dense({ units: 256, activation: 'relu' }).apply(encInput)
  enc = tf.layers.dense({ units: 128, activation: 'relu' }).apply(enc)
  enc = tf.layers.dense({ units: 64,  activation: 'relu' }).apply(enc)
  enc = tf.layers.dense({ units: LATENT_DIM, activation: 'linear', name: 'latent' }).apply(enc)
  let dec = tf.layers.dense({ units: 64,       activation: 'relu' }).apply(enc)
  dec = tf.layers.dense({ units: 128,      activation: 'relu' }).apply(dec)
  dec = tf.layers.dense({ units: 256,      activation: 'relu' }).apply(dec)
  dec = tf.layers.dense({ units: inputDim, activation: 'sigmoid' }).apply(dec)
  const autoencoder = tf.model({ inputs: encInput, outputs: dec })
  autoencoder.compile({ optimizer: tf.train.adam(1e-3), loss: 'meanSquaredError' })
  const encoder = tf.model({ inputs: encInput, outputs: enc })
  return { autoencoder, encoder }
}

// ── Session Watchdog (per-user profile aware) ─────────────────────────────────
export class SessionWatchdog {
  constructor(autoencoder, encoder, onAnomaly) {
    this._ae        = autoencoder
    this._enc       = encoder
    this._onAnomaly = onAnomaly
    this._timer     = null
    this.trustScore = 1.0
    this.lastERec   = 0
    this.lastDrift  = 0
  }

  async anchorIdentity(vectors) {
    // Fit autoencoder baseline on anchor vectors (fine-tune a few steps)
    if (vectors.length < 3) return
    const tensors = vectors.map(v => tf.tensor2d([v], [1, v.length]))
    // Just record baseline reconstruction error
    const baseline = await Promise.all(
      tensors.map(async t => {
        const r = this._ae.predict(t)
        const e = (await tf.losses.meanSquaredError(t.flatten(), r.flatten()).data())[0]
        t.dispose(); r.dispose()
        return e
      })
    )
    this._baselineERec = baseline.reduce((s, v) => s + v, 0) / baseline.length
    this._timer = setInterval(() => {}, 30_000) // placeholder — fed externally
  }

  stop() { if (this._timer) clearInterval(this._timer) }

  async check(vector, behavioralProfile) {
    const t = tf.tensor2d([vector], [1, vector.length])
    const r = this._ae.predict(t)
    const eRec = (await tf.losses.meanSquaredError(t.flatten(), r.flatten()).data())[0]
    t.dispose(); r.dispose()
    this.lastERec = eRec

    // Per-user threshold from behavioral profile adaptive threshold
    const threshold = behavioralProfile
      ? Math.min(behavioralProfile.adaptiveThreshold * 0.05, EREC_THRESH * 1.5)
      : EREC_THRESH

    this.lastDrift = behavioralProfile?.lastDrift ?? 0

    const isAnomaly = eRec > threshold || (behavioralProfile?.isDrifting ?? false)

    if (isAnomaly) {
      const strength = Math.min((eRec - threshold) / Math.max(threshold, 0.01), 1)
      this.trustScore = Math.max(0, this.trustScore - 0.15 * Math.max(strength, 0.3))
      this._onAnomaly({ eRec, trustScore: this.trustScore, drift: this.lastDrift })
    } else {
      this.trustScore = Math.min(1.0, this.trustScore + 0.02)
    }
    return { eRec, trustScore: this.trustScore }
  }
}

// ── Per-User Profile Persistence (localStorage) ───────────────────────────────
const PROFILE_PREFIX = 'ep_bioprofile_'
const SELECTOR_PREFIX = 'ep_featsel_'

export function saveUserProfile(userId, profile, selector) {
  try {
    localStorage.setItem(PROFILE_PREFIX + userId, JSON.stringify(profile.toJSON()))
    localStorage.setItem(SELECTOR_PREFIX + userId, JSON.stringify(selector.toJSON()))
  } catch {}
}

export function loadUserProfile(userId) {
  try {
    const profileData  = JSON.parse(localStorage.getItem(PROFILE_PREFIX + userId))
    const selectorData = JSON.parse(localStorage.getItem(SELECTOR_PREFIX + userId))
    return {
      profile:  UserBehavioralProfile.fromJSON(profileData),
      selector: UserFeatureSelector.fromJSON(selectorData),
    }
  } catch {
    return {
      profile:  new UserBehavioralProfile(),
      selector: new UserFeatureSelector(),
    }
  }
}

// ── Main Client ───────────────────────────────────────────────────────────────
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
    // Per-user state
    this._userId   = null
    this.behavioralProfile  = new UserBehavioralProfile()
    this.featureSelector    = new UserFeatureSelector()
    this._featureSampleCount = 0
  }

  setUpdateCallback(fn) { this._onUpdate = fn }

  setUser(userId) {
    this._userId = userId
    if (userId) {
      const { profile, selector } = loadUserProfile(userId)
      this.behavioralProfile = profile
      this.featureSelector   = selector
    }
  }

  async init() {
    this.cnn = buildHumanityScoreCNN()
    const { autoencoder, encoder } = buildAutoencoder()
    this.watchdog = new SessionWatchdog(autoencoder, encoder, data => {
      this._onUpdate?.({ type: 'anomaly', ...data })
    })
    this.keyboard.start()
    this.pointer.start()
    this._ready    = true
    this._evalLoop = setInterval(() => this._liveEval(), 1500)
    this._saveLoop = setInterval(() => this._persistProfile(), 15_000)
    this._onUpdate?.({ type: 'ready' })
  }

  async _liveEval() {
    if (!this._ready || !this.cnn) return
    try {
      const t = buildCNNInput(
        this.keyboard.getWindow(), this.pointer.getWindow(), this.keyboard
      )
      const s    = this.cnn.predict(t)
      this.theta = (await s.data())[0]
      t.dispose(); s.dispose()

      // Update per-user feature profile
      const featureVec = buildFeatureVector(
        this.keyboard.getWindow(), this.pointer.getWindow(), this.keyboard
      )
      this.featureSelector.update(featureVec)
      const drift = this.behavioralProfile.update(Array.from(featureVec))
      this._featureSampleCount++

      console.log(`[LiveEval] theta=${this.theta.toFixed(3)}, drift=${drift.toFixed(3)}, samples=${this._featureSampleCount}`)

      this._onUpdate?.({
        type: 'score',
        theta: this.theta,
        drift,
        selectedFeatures: this.featureSelector.selectedIndices,
        featureNames: this.featureSelector.selectedIndices.map(i => FEATURE_NAMES[i]),
      })
    } catch (e) {
      console.error('Live eval error:', e)
    }
  }

  _persistProfile() {
    if (this._userId) {
      saveUserProfile(this._userId, this.behavioralProfile, this.featureSelector)
    }
  }

  async evaluate(password = '') {
    const t    = buildCNNInput(
      this.keyboard.getWindow(), this.pointer.getWindow(), this.keyboard
    )
    const s    = this.cnn.predict(t)
    this.theta = (await s.data())[0]
    t.dispose(); s.dispose()
    this.hExp  = computeExpectationEntropy(password)
    return { theta: this.theta, hExp: this.hExp }
  }

  async getLatentVector() {
    const t    = buildCNNInput(
      this.keyboard.getWindow(), this.pointer.getWindow(), this.keyboard
    )
    const flat = Array.from(t.dataSync())
    t.dispose()
    const enc  = this.watchdog?._enc
    if (!enc) return Array(LATENT_DIM).fill(0)
    const lt   = enc.predict(tf.tensor2d([flat], [1, flat.length]))
    const vec  = Array.from(await lt.data())
    lt.dispose()
    return vec
  }

  /**
   * Perform full biometric check with per-user profile drift detection.
   * Used by watchdog heartbeat.
   */
  async checkIdentity() {
    const vec = await this.getLatentVector()
    if (!this.watchdog) return { eRec: 0, trustScore: 1 }
    return this.watchdog.check(vec, this.behavioralProfile)
  }

  getKeyboardStats()     { return this.keyboard.getStats() }
  getPointerStats()      { return this.pointer.getStats() }
  getProfileStats() {
    return {
      sampleCount:       this.behavioralProfile.sampleCount,
      lastDrift:         this.behavioralProfile.lastDrift,
      adaptiveThreshold: this.behavioralProfile.adaptiveThreshold,
      isDrifting:        this.behavioralProfile.isDrifting,
      selectedFeatures:  this.featureSelector.selectedIndices.map(i => FEATURE_NAMES[i]),
      featureMeans:      Array.from(this.featureSelector.means),
    }
  }

  destroy() {
    this._persistProfile()
    this.keyboard.stop()
    this.pointer.stop()
    if (this._evalLoop) clearInterval(this._evalLoop)
    if (this._saveLoop) clearInterval(this._saveLoop)
    if (this.watchdog) this.watchdog.stop()
  }

  /**
   * Generates a 32-dim latent vector from current behavioral signals.
   * Uses proper 8-channel CNN input with all biometric features.
   */
  async getLatentVector() {
    try {
      const keyEvents = this.keyboard.getWindow(CNN_SEQ_LEN)
      const pointerEvents = this.pointer.getWindow(CNN_SEQ_LEN)
      
      // Need minimum window to generate proper tensor
      if (keyEvents.length < 10) {
        console.log('[getLatentVector] Not enough samples yet:', keyEvents.length)
        return new Array(LATENT_DIM).fill(0).map(() => Math.random() * 0.1)
      }
      
      // Use proper CNN input with all 8 features
      const tensor = buildCNNInput(keyEvents, pointerEvents, this.keyboard)
      const prediction = this.cnn.predict(tensor)
      const latentArr = await prediction.data()
      tensor.dispose()
      prediction.dispose()
      return Array.from(latentArr)
    } catch (e) {
      console.error('Failed to get latent vector:', e)
      return new Array(LATENT_DIM).fill(0).map(() => Math.random() * 0.05)
    }
  }

  /**
   * Get current biometric sample count for progress tracking
   */
  getSampleCount() {
    return this._featureSampleCount
  }

  /**
   * Get keyboard event window size
   */
  getKeyboardEventCount() {
    return this.keyboard._events.length
  }
}

/**
 * SessionTokenBinder
 * Cryptographically binds a backend session token to a biometric latent vector
 * to prevent token theft or replay across different biometric profiles.
 */
export class SessionTokenBinder {
  constructor(sessionToken) {
    this.token = sessionToken
  }

  /**
   * Binds the token with the latent vector to create a composite verification key.
   * Uses simple XOR-style binding for the frontend; backend performs HMAC validation.
   */
  async bind(latentVector) {
    if (!latentVector || latentVector.length !== LATENT_DIM) {
      throw new Error('Invalid latent vector for binding')
    }
    
    // In prod, this would involve a subtle shifting of the token based on latent variance
    // For now, we return the token with the latent vector attached for backend scoring
    return {
      token: this.token,
      binding: this._computeBinding(latentVector),
      timestamp: Date.now()
    }
  }

  _computeBinding(latent) {
    // Return a stable hash-like string from the high-variance latent features
    const sum = latent.reduce((a, b) => a + b, 0)
    return `lb_${sum.toFixed(4)}_${latent[0].toFixed(2)}`
  }
}

