/**
 * Entropy Prime — Biometrics Engine (Browser-side)
 * All raw signals are processed here. Only θ and latent vectors leave the browser.
 */
import * as tf from '@tensorflow/tfjs'

const CNN_SEQ_LEN  = 50
const CNN_FEATURES = 4   // dwell, flight, speed, jitter
const LATENT_DIM   = 32
const EREC_THRESH  = 0.18

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

// ─── Keyboard Collector ───────────────────────────────────────────────────────
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
    const eRec = (await tf.losses.meanSquaredError(t.flatten(), r.flatten()).data())[0]
    t.dispose(); r.dispose()
    this.lastERec = eRec
    if (eRec > EREC_THRESH) {
      const strength = Math.min((eRec - EREC_THRESH) / EREC_THRESH, 1)
      this.trustScore = Math.max(0, this.trustScore - 0.15 * strength)
      this._onAnomaly({ eRec, trustScore: this.trustScore })
    } else {
      this.trustScore = Math.min(1.0, this.trustScore + 0.02)
    }
    return { eRec, trustScore: this.trustScore }
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
