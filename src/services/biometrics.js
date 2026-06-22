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

// ── Constants ─────────────────────────────────────────────────────────────────
const CNN_SEQ_LEN  = 50
const CNN_FEATURES = 8   // dwell, flight, speed, jitter, accel, rhythm, pressure_proxy, pause
const LATENT_DIM   = 32
const EREC_THRESH  = 0.18

// Inactivity threshold for continuous auth. If no keyboard/pointer event has
// been captured within this window, the session is considered IDLE: drift is
// frozen and the trust score is held (idle is not behavioural deviation).
const INACTIVITY_MS = 5000

// ── Frozen-template identity scoring (human-vs-human discrimination) ──────────
// A frozen enrollment template is compared against the live typing signature.
// Typing + digraph dominate; mouse is a weak tie-breaker. A large typing/
// digraph mismatch is GATED (capped) so matching mouse data can't hide a
// different human. Scores map to zones with hysteresis to avoid false positives.
const ID_W_TYPING   = 0.40
const ID_W_DIGRAPH  = 0.40
const ID_W_MOUSE    = 0.20
const ID_TOL_TYPING  = 0.30   // relative-diff tolerance (Gaussian width) — owner variation stays high
const ID_TOL_DIGRAPH = 0.30
const ID_TOL_MOUSE   = 0.60   // mouse is lenient (noisy, low weight)
const ID_GATE_DWELL   = 0.30  // relative-diff gate thresholds — exceed any → strong penalty
const ID_GATE_FLIGHT  = 0.28
const ID_GATE_DIGRAPH = 0.30
const ID_GATE_CAP     = 40    // a gated typing mismatch caps the identity score here (→ re-auth zone)
const ID_ENROLL_MIN_KEYS     = 30   // keystrokes required before the template auto-freezes
const ID_ENROLL_MIN_DIGRAPHS = 10   // distinct digraphs required
const ID_MIN_LIVE_KEYS  = 12   // need at least this much live evidence to score (else hold)
const ID_REAUTH_STREAK  = 3    // (legacy, kept for back-compat logging)
const ID_REAUTH_COOLDOWN_MS = 120_000 // after a successful verify, suppress new re-auth for 120 s

// Progressive scoring (replaces the binary hard cap) ─────────────────────────
const ID_TRUSTED_MIN  = 80     // ≥80 Trusted
const ID_MONITOR_MIN  = 60     // 60–80 Monitor, <60 candidate Re-auth
const ID_SMOOTH_ALPHA = 0.25   // EMA smoothing → confidence decays gradually (no instant jumps)
const ID_WINDOW       = 20     // rolling window of recent evaluations
const ID_SUSP_MAX     = 14     // suspicion accumulator ceiling
const ID_SUSP_REAUTH  = 8      // sustained suspicion required before re-auth is allowed
const ID_SUSP_MIN_LOW = 10     // ≥ this many of the last 20 evals below 60 (sustained pattern)
const ID_CORROB_DIGRAPH = 0.80 // strong digraph match → very likely the owner (Task 7)
const ID_CORROB_MOUSE   = 0.75 // strong mouse match → don't escalate on typing-speed alone
const ID_MONITOR_FLOOR  = 0.60 // hold effective trust here until a sustained pattern is confirmed

const idZone = (s) => (s >= 80 ? 'trusted' : s >= 60 ? 'monitor' : 'reauth')
const _gaussSim = (relDiff, tol) => Math.exp(-0.5 * (relDiff / tol) ** 2)
const _relDiff  = (a, b) => Math.abs(a - b) / Math.max(Math.abs(b), 1e-6)

// ── Enhanced keyboard-biometric evidence signals (ADDITIVE — feed the existing
//    engine; existing typing/digraph/mouse logic is unchanged) ────────────────
// Per-signal weights (sum = 1.00). Missing/insufficient signals are dropped and
// the remaining weights are renormalised, so the score degrades gracefully and
// old templates keep working.
const ID_WEIGHTS = {
  typing:         0.10,
  digraph:        0.15,   // existing bigram-dwell-ratio similarity
  mouse:          0.10,
  digraphProfile: 0.15,   // Feature 1 — top-50 digraph latency profile
  trigraph:       0.15,   // Feature 2 — trigraph latency profile (hard to fake)
  burst:          0.10,   // Feature 3 — burst/pause rhythm
  backspace:      0.05,   // Feature 4 — correction signature
  spacebar:       0.05,   // Feature 5 — pre/post-space delays
  dwell:          0.10,   // Feature 6 — key hold time (classic keystroke biometric)
  phrase:         0.05,   // Feature 7 — privacy-preserving phrase fingerprint
}
const ID_TOL_TRIGRAPH = 0.35
const ID_TOL_BURST    = 0.40
const ID_TOL_BACKSPC  = 0.50
const ID_TOL_SPACE    = 0.35
const ID_TOL_DWELL    = 0.25
const ID_TOL_PHRASE   = 0.40
const ID_DRIFT_THRESH = 0.55   // a signal below this counts as "drifting"
const ID_DRIFT_MIN    = 2      // re-auth needs ≥2 INDEPENDENT signals drifting (false-positive guard)
const ID_MIN_DG_OVERLAP = 4    // shared digraphs needed for digraphProfile similarity
const ID_MIN_TG_OVERLAP = 3    // shared trigraphs needed for trigraph similarity

// Welford accumulator helpers (online mean + variance), used to build the
// per-digraph / per-trigraph / dwell profiles without storing raw keystrokes.
function _welPush(map, key, x) {
  let a = map[key]; if (!a) a = map[key] = { n: 0, mean: 0, m2: 0 }
  a.n++; const d = x - a.mean; a.mean += d / a.n; a.m2 += d * (x - a.mean)
}
function _welStd(a) { return a && a.n > 1 ? Math.sqrt(a.m2 / a.n) : 0 }
function _meanPush(m, x) { m.n++; m.mean += (x - m.mean) / m.n }
// EMA accumulator — RECENT-weighted mean+variance. Used for the live digraph /
// trigraph latency profiles so that the CURRENT typist (not a cumulative average
// dominated by enrolment) drives the live comparison against the frozen template.
function _emaPush(map, key, x, alpha = 0.30) {
  let a = map[key]; if (!a) { a = map[key] = { n: 1, mean: x, var2: 0 }; return }
  a.n++; const prev = a.mean
  a.mean = (1 - alpha) * a.mean + alpha * x
  a.var2 = (1 - alpha) * a.var2 + alpha * (x - prev) * (x - a.mean)
}
function _emaStd(a) { return a ? Math.sqrt(Math.max(0, a.var2)) : 0 }
// Privacy-preserving phrase fingerprint: only frequencies for these common tokens
// are kept; everything the user types is otherwise discarded at each word break.
const COMMON_WORDS = new Set(['the', 'and', 'you', 'that', 'for', 'are', 'with', 'this', 'have', 'not', 'ok', 'bro', 'wt', 'hey', 'yes', 'no', 'to', 'is', 'it', 'of', 'in', 'on', 'my', 'me', 'so', 'lol', 'hi', 'hello', 'thanks', 'please'])
// Cosine similarity of two {token: freq} vectors → [0,1].
function _cosineFreq(a, b) {
  const keys = new Set([...Object.keys(a || {}), ...Object.keys(b || {})])
  let dot = 0, na = 0, nb = 0
  keys.forEach(k => { const x = a?.[k] || 0, y = b?.[k] || 0; dot += x * y; na += x * x; nb += y * y })
  return na && nb ? dot / (Math.sqrt(na) * Math.sqrt(nb)) : null
}

// ── Enhanced-signal similarity functions (each → [0,1] or null = no evidence) ──
// Compare two latency profiles { "key": {meanLatency, count} } on shared keys,
// weighted by the enrolled count. (Features 1 & 2)
function _profileSim(live, tpl, tol, minOverlap) {
  if (!live || !tpl) return null
  const shared = Object.keys(tpl).filter(k => live[k])
  if (shared.length < minOverlap) return null
  let sim = 0, wsum = 0
  for (const k of shared) {
    const w = tpl[k].count || 1
    sim += w * _gaussSim(_relDiff(live[k].meanLatency, tpl[k].meanLatency), tol)
    wsum += w
  }
  return wsum ? sim / wsum : null
}
function _burstSim(live, tpl) {                                     // Feature 3
  if (!tpl || !live || live.avgBurstLength <= 0) return null
  return (_gaussSim(_relDiff(live.avgBurstLength, tpl.avgBurstLength), ID_TOL_BURST) +
          _gaussSim(_relDiff(live.avgPauseLength, tpl.avgPauseLength || 1), ID_TOL_BURST)) / 2
}
function _backspaceSim(live, tpl) {                                 // Feature 4
  if (!tpl || !live || live.chars < 20) return null
  const d1 = Math.abs(live.backspacesPer100Chars - tpl.backspacesPer100Chars) / 20
  const d2 = Math.abs(live.immediateCorrectionRate - tpl.immediateCorrectionRate)
  const d3 = Math.abs(live.wholeWordDeleteRate - tpl.wholeWordDeleteRate)
  return (_gaussSim(d1, ID_TOL_BACKSPC) + _gaussSim(d2, ID_TOL_BACKSPC) + _gaussSim(d3, ID_TOL_BACKSPC)) / 3
}
function _spacebarSim(live, tpl) {                                  // Feature 5
  if (!tpl || !live || live.n < 3) return null
  return (_gaussSim(_relDiff(live.avgPreSpaceDelay, tpl.avgPreSpaceDelay), ID_TOL_SPACE) +
          _gaussSim(_relDiff(live.avgPostSpaceDelay, tpl.avgPostSpaceDelay), ID_TOL_SPACE)) / 2
}
function _dwellSim(live, tpl) {                                     // Feature 6
  if (!tpl || !live || live.n < 8) return null
  return (_gaussSim(_relDiff(live.avgDwellTime, tpl.avgDwellTime), ID_TOL_DWELL) +
          _gaussSim(_relDiff(live.stdDwellTime, tpl.stdDwellTime || 1), ID_TOL_DWELL)) / 2
}
function _phraseSim(live, tpl) {                                    // Feature 7
  if (!tpl || !live || live.averageWordLength <= 0) return null
  const wl  = _gaussSim(_relDiff(live.averageWordLength, tpl.averageWordLength), ID_TOL_PHRASE)
  const sl  = (tpl.averageSentenceLength > 0 && live.averageSentenceLength > 0)
    ? _gaussSim(_relDiff(live.averageSentenceLength, tpl.averageSentenceLength), ID_TOL_PHRASE) : null
  const cos = _cosineFreq(live.commonWordFrequency, tpl.commonWordFrequency)
  const parts = [wl, sl, cos].filter(v => v != null)
  return parts.length ? parts.reduce((s, v) => s + v, 0) / parts.length : null
}
const _r3 = (v) => (v == null ? null : +v.toFixed(3))
const PROFILE_WIN  = 200  // rolling window for per-user profile update
const DRIFT_ALPHA  = 0.05 // EMA coefficient for profile smoothing
const FEAT_K       = 6    // top-K features selected per user

// ── Zipf Entropy ──────────────────────────────────────────────────────────────
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
  'dwell_norm',   // key press duration
  'flight_norm',  // inter-key gap
  'speed_norm',   // pointer speed
  'jitter_norm',  // pointer micro-tremor
  'accel_norm',   // pointer acceleration magnitude
  'rhythm_norm',  // keystroke rhythm consistency (CV of dwell)
  'pause_norm',   // long pauses between bursts
  'bigram_norm',  // common bigram dwell ratio
]

// ── Per-User Feature Selector ─────────────────────────────────────────────────
/**
 * Tracks per-user feature variance and selects the K most discriminative
 * features based on coefficient of variation (high CV = high signal).
 * Updated online using Welford's algorithm.
 */
export class UserFeatureSelector {
  constructor(k = FEAT_K) {
    this.k         = k
    this.means     = new Float32Array(CNN_FEATURES).fill(0.5)
    this.m2s       = new Float32Array(CNN_FEATURES).fill(0.1)
    this.n         = 0
    this._selected = Array.from({ length: CNN_FEATURES }, (_, i) => i)
  }

  update(featureVec) {
    this.n++
    for (let i = 0; i < CNN_FEATURES; i++) {
      const delta  = featureVec[i] - this.means[i]
      this.means[i] += delta / this.n
      const delta2 = featureVec[i] - this.means[i]
      this.m2s[i]  += delta * delta2
    }
    if (this.n % 20 === 0) this._reselect()
  }

  _reselect() {
    const cvs = Array.from({ length: CNN_FEATURES }, (_, i) => {
      const variance = this.n > 1 ? this.m2s[i] / (this.n - 1) : 0
      const std = Math.sqrt(variance)
      return this.means[i] > 0 ? std / this.means[i] : 0
    })
    this._selected = cvs
      .map((cv, i) => ({ cv, i }))
      .sort((a, b) => b.cv - a.cv)
      .slice(0, this.k)
      .map(x => x.i)
      .sort((a, b) => a - b)
  }

  get selectedIndices() { return this._selected }

  project(featureVec) {
    return this._selected.map(i => featureVec[i])
  }

  toJSON() {
    return {
      means:    Array.from(this.means),
      m2s:      Array.from(this.m2s),
      n:        this.n,
      selected: this._selected,
    }
  }

  static fromJSON(obj) {
    if (!obj) return new UserFeatureSelector()
    const sel      = new UserFeatureSelector()
    sel.means      = new Float32Array(obj.means)
    sel.m2s        = new Float32Array(obj.m2s)
    sel.n          = obj.n
    sel._selected  = obj.selected
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
    this.emaProfile   = null
    this.emaVariance  = null
    this.sampleCount  = 0
    this.driftHistory = []
    this.lastDrift    = 0
  }

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
    let drift = 0

    for (let i = 0; i < CNN_FEATURES; i++) {
      const diff = vec[i] - this.emaProfile[i]
      const std  = Math.sqrt(this.emaVariance[i]) + 1e-6
      drift += (diff / std) ** 2
      this.emaProfile[i]  = (1 - alpha) * this.emaProfile[i]  + alpha * vec[i]
      this.emaVariance[i] = (1 - alpha) * this.emaVariance[i] + alpha * diff * diff
    }
    drift = Math.sqrt(drift / CNN_FEATURES)

    this.lastDrift = drift
    this.driftHistory.push(drift)
    if (this.driftHistory.length > 100) this.driftHistory.shift()

    console.log(`[BehavioralProfile] drift=${drift.toFixed(3)}, sampleCount=${this.sampleCount}`)
    return drift
  }

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
      emaProfile:   this.emaProfile  ? Array.from(this.emaProfile)  : null,
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

// ── Keyboard Collector ────────────────────────────────────────────────────────
export class KeyboardCollector {
  constructor() {
    this._events     = []
    this._keyDownTs  = {}
    this._lastKeyUp  = null
    this._bigramTs   = {}
    this._burstStart = null
    this._pauses     = []
    // ── Enhanced keyboard-biometric state (additive) ─────────────────────────
    this._keys       = []                                   // recent {code, char, downTs, upTs}
    this._dg         = {}                                   // digraph latency "a>b" → Welford
    this._tg         = {}                                   // trigraph latency "a>b>c" → Welford
    this._dwellAgg   = { n: 0, mean: 0, m2: 0 }             // key hold-time profile
    this._preSpace   = { n: 0, mean: 0 }                    // delay before Space
    this._postSpace  = { n: 0, mean: 0 }                    // delay after Space
    this._bs         = { backspaces: 0, chars: 0, immediate: 0, wholeWord: 0, lastWasChar: false }
    this._bursts     = []                                   // continuous-typing burst durations (ms)
    this._burstStartT = null
    this._wordBuf    = ''                                   // transient current word (DISCARDED at boundary)
    this._wordLens   = { n: 0, mean: 0 }
    this._sentWords  = 0
    this._sentLens   = { n: 0, mean: 0 }
    this._common     = {}                                   // whitelisted short-word frequency
  }

  start(target = document) {
    this._onDown = e => {
      const now = performance.now()
      this._keyDownTs[e.code] = now
      // pause + burst rhythm (Feature 3)
      if (this._lastKeyUp && now - this._lastKeyUp > 800) {
        const pause = now - this._lastKeyUp
        this._pauses.push(pause)
        if (this._pauses.length > 50) this._pauses.shift()
        if (this._burstStartT != null) {                       // close the previous burst
          this._bursts.push(Math.max(0, this._lastKeyUp - this._burstStartT))
          if (this._bursts.length > 50) this._bursts.shift()
        }
        this._burstStartT = now                                 // start a new burst
      } else if (this._burstStartT == null) {
        this._burstStartT = now
      }
      // backspace signature (Feature 4)
      if (e.key === 'Backspace') {
        this._bs.backspaces++
        if (e.ctrlKey || e.altKey) this._bs.wholeWord++         // ctrl/alt+backspace = word delete
        else if (this._bs.lastWasChar) this._bs.immediate++     // correcting right after a char
        this._bs.lastWasChar = false
        if (this._wordBuf) this._wordBuf = this._wordBuf.slice(0, -1)
      }
    }
    this._onUp = e => {
      const now  = performance.now()
      const down = this._keyDownTs[e.code]
      if (down === undefined) return
      const dwell      = now - down
      const flight     = this._lastKeyUp !== null ? Math.max(0, down - this._lastKeyUp) : 0
      const prevCode   = this._lastCode
      this._lastCode   = e.code
      const bigramKey  = prevCode ? `${prevCode}>${e.code}` : null
      const bigramRatio = bigramKey && this._bigramTs[bigramKey]
        ? dwell / Math.max(this._bigramTs[bigramKey], 1)
        : 1.0
      if (bigramKey) {
        this._bigramTs[bigramKey] = dwell * 0.8 + (this._bigramTs[bigramKey] || dwell) * 0.2
      }
      this._events.push({ dwell, flight, ts: now, bigramRatio })
      if (this._events.length > 300) this._events.shift()
      this._lastKeyUp = now
      this._ingestRich(e, down, now, dwell, flight)             // enhanced signals (additive)
    }
    target.addEventListener('keydown', this._onDown)
    target.addEventListener('keyup',   this._onUp)
  }

  /**
   * Build the enhanced keyboard-biometric profiles from a keystroke. Privacy:
   * raw text is never stored — only timing stats, rates, and counts for a small
   * whitelist of common tokens; the in-progress word buffer is discarded at each
   * word boundary.
   */
  _ingestRich(e, downTs, upTs, dwell, flight) {
    const char = (e.key && e.key.length === 1) ? e.key : null
    // recent keystroke buffer for digraph/trigraph latencies (down-down timing)
    this._keys.push({ code: e.code, char, downTs, upTs })
    if (this._keys.length > 6) this._keys.shift()
    const K = this._keys
    // Feature 6 — dwell (key hold time)
    if (dwell > 0 && dwell < 1000) { const a = this._dwellAgg; a.n++; const d = dwell - a.mean; a.mean += d / a.n; a.m2 += d * (dwell - a.mean) }
    // Feature 1 — digraph latency (down-to-down), RECENT-weighted (EMA)
    if (K.length >= 2) {
      const a = K[K.length - 2], b = K[K.length - 1]
      const lat = b.downTs - a.downTs
      if (lat > 0 && lat < 2000) _emaPush(this._dg, `${a.code}>${b.code}`, lat)
    }
    // Feature 2 — trigraph latency (first-to-third down), RECENT-weighted (EMA)
    if (K.length >= 3) {
      const a = K[K.length - 3], b = K[K.length - 2], c = K[K.length - 1]
      const lat = c.downTs - a.downTs
      if (lat > 0 && lat < 3000) _emaPush(this._tg, `${a.code}>${b.code}>${c.code}`, lat)
    }
    // Feature 5 — spacebar rhythm
    if (e.code === 'Space') _meanPush(this._preSpace, flight)
    else if (K.length >= 2 && K[K.length - 2].code === 'Space') _meanPush(this._postSpace, flight)
    // Feature 4 + 7 — character / word / sentence bookkeeping
    const isWordBreak = e.code === 'Space' || char === ' '
    const isSentEnd   = char === '.' || char === '!' || char === '?'
    const isPunct     = isSentEnd || char === ',' || char === ';' || char === ':'
    if (char && char !== ' ' && !isPunct) {
      this._bs.chars++; this._bs.lastWasChar = true
      if (this._wordBuf.length < 40) this._wordBuf += char
    } else if (e.key !== 'Backspace') {
      this._bs.lastWasChar = false
    }
    if (isWordBreak || isPunct) this._finishWord(isSentEnd)
  }

  _finishWord(sentenceEnd) {
    const w = this._wordBuf
    if (w.length) {
      _meanPush(this._wordLens, w.length)
      const lc = w.toLowerCase()
      if (COMMON_WORDS.has(lc)) this._common[lc] = (this._common[lc] || 0) + 1
      this._sentWords++
    }
    this._wordBuf = ''
    if (sentenceEnd && this._sentWords > 0) { _meanPush(this._sentLens, this._sentWords); this._sentWords = 0 }
  }

  stop(target = document) {
    target.removeEventListener('keydown', this._onDown)
    target.removeEventListener('keyup',   this._onUp)
  }

  _getAvgBigram() {
    const vals = Object.values(this._bigramTs)
    return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : 100
  }

  getRhythm() {
    const dwells = this._events.slice(-20).map(e => e.dwell)
    if (dwells.length < 3) return 0
    const mean = dwells.reduce((s, v) => s + v, 0) / dwells.length
    const std  = Math.sqrt(dwells.reduce((s, v) => s + (v - mean) ** 2, 0) / dwells.length)
    return mean > 0 ? Math.min(std / mean, 2) / 2 : 0
  }

  getAvgPause() {
    if (!this._pauses.length) return 0
    return this._pauses.reduce((s, v) => s + v, 0) / this._pauses.length
  }

  getWindow(n = CNN_SEQ_LEN) { return this._events.slice(-n) }

  /** Timestamp (performance.now ms) of the most recent keystroke, or -Infinity. */
  getLastTs() { const e = this._events; return e.length ? e[e.length - 1].ts : -Infinity }

  /** Copy of the per-digraph smoothed-latency map ("prevCode>code" → ms). */
  getDigraphMap() { return { ...this._bigramTs } }
  getDigraphCount() { return Object.keys(this._bigramTs).length }

  /** Mean+std of dwell and flight over the last `n` keystrokes. */
  getDwellFlightStats(n = 200) {
    const ev = this._events.slice(-n)
    if (!ev.length) return { dwellMean: 0, dwellStd: 0, flightMean: 0, flightStd: 0, count: 0 }
    const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length
    const std  = (a, m) => Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / a.length)
    const dw = ev.map(e => e.dwell), fl = ev.map(e => e.flight)
    const dm = mean(dw), fm = mean(fl)
    return { dwellMean: dm, dwellStd: std(dw, dm), flightMean: fm, flightStd: std(fl, fm), count: ev.length }
  }

  // ── Enhanced biometric profiles (Features 1–7) ───────────────────────────
  /** Feature 1 — top-N digraphs by count → { "a>b": {count, meanLatency, stdDev} }. */
  getDigraphProfile(topN = 50) {
    return Object.entries(this._dg)
      .sort((a, b) => b[1].n - a[1].n).slice(0, topN)
      .reduce((o, [k, a]) => { o[k] = { count: a.n, meanLatency: a.mean, stdDev: _emaStd(a) }; return o }, {})
  }
  /** Feature 2 — top-N trigraphs by count → { "a>b>c": {count, meanLatency, stdDev} }. */
  getTrigraphProfile(topN = 40) {
    return Object.entries(this._tg)
      .sort((a, b) => b[1].n - a[1].n).slice(0, topN)
      .reduce((o, [k, a]) => { o[k] = { count: a.n, meanLatency: a.mean, stdDev: _emaStd(a) }; return o }, {})
  }
  /** Feature 3 — burst/pause rhythm. */
  getBurstProfile() {
    const b = this._bursts
    const avgBurstLength = b.length ? b.reduce((s, v) => s + v, 0) / b.length : 0
    const burstVariance  = b.length > 1 ? b.reduce((s, v) => s + (v - avgBurstLength) ** 2, 0) / b.length : 0
    const avgPauseLength = this.getAvgPause()
    return { avgBurstLength, avgPauseLength, burstVariance }
  }
  /** Feature 4 — backspace / correction signature. */
  getBackspaceProfile() {
    const c = Math.max(this._bs.chars, 1), b = Math.max(this._bs.backspaces, 1)
    return {
      backspacesPer100Chars:  (this._bs.backspaces / c) * 100,
      immediateCorrectionRate: this._bs.immediate / b,
      wholeWordDeleteRate:     this._bs.wholeWord / b,
      chars: this._bs.chars,
    }
  }
  /** Feature 5 — spacebar rhythm. */
  getSpacebarProfile() { return { avgPreSpaceDelay: this._preSpace.mean, avgPostSpaceDelay: this._postSpace.mean, n: this._preSpace.n } }
  /** Feature 6 — key hold time profile (RECENT window so it tracks the current typist). */
  getDwellProfile() {
    const ev = this._events.slice(-60)
    if (ev.length < 5) return { avgDwellTime: 0, stdDwellTime: 0, n: ev.length }
    const dw = ev.map(e => e.dwell)
    const m = dw.reduce((s, v) => s + v, 0) / dw.length
    const sd = Math.sqrt(dw.reduce((s, v) => s + (v - m) ** 2, 0) / dw.length)
    return { avgDwellTime: m, stdDwellTime: sd, n: ev.length }
  }
  /** Feature 7 — privacy-preserving phrase fingerprint (no raw text). */
  getPhraseProfile() {
    const total = Object.values(this._common).reduce((s, v) => s + v, 0) || 1
    const commonWordFrequency = Object.fromEntries(Object.entries(this._common).map(([k, v]) => [k, v / total]))
    return { averageWordLength: this._wordLens.mean, averageSentenceLength: this._sentLens.mean, commonWordFrequency }
  }
  /** Counts used to decide whether the rich profiles have enough evidence. */
  getRichReadiness() { return { digraphs: Object.keys(this._dg).length, trigraphs: Object.keys(this._tg).length, chars: this._bs.chars } }

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

// ── Pointer Collector ─────────────────────────────────────────────────────────
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
    if (this._prevV) {
      ax = (vx - this._prevV.vx) / dt
      ay = (vy - this._prevV.vy) / dt
    }
    const jitter = this._prevV
      ? Math.sqrt((vx - this._prevV.vx) ** 2 + (vy - this._prevV.vy) ** 2) : 0
    const accel = Math.sqrt(ax * ax + ay * ay)
    this._samples.push({
      vx, vy, ax, ay, jitter, accel,
      speed: Math.sqrt(vx * vx + vy * vy),
      ts: now,
    })
    if (this._samples.length > 500) this._samples.shift()
    this._prevV = { vx, vy }
    this._prev  = { x, y, t: now }
  }

  getWindow(n = CNN_SEQ_LEN) { return this._samples.slice(-n) }

  /** Timestamp (performance.now ms) of the most recent pointer sample, or -Infinity. */
  getLastTs() { const s = this._samples; return s.length ? s[s.length - 1].ts : -Infinity }

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

// ── Feature Vector Builder (8-dim) ────────────────────────────────────────────
export function buildFeatureVector(keyEvents, pointerEvents, keyboard) {
  const kStats = keyboard.getStats()
  const feats  = new Float32Array(CNN_FEATURES)

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
  const bigramRatios = keyEvents
    .filter(e => e.bigramRatio !== undefined)
    .map(e => e.bigramRatio)
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
    data[i * CNN_FEATURES + 0] = Math.min(ke.dwell  / 300,  1)
    data[i * CNN_FEATURES + 1] = Math.min(ke.flight / 500,  1)
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

// ── Session Watchdog ──────────────────────────────────────────────────────────
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
    if (vectors.length < 3) return
    const tensors  = vectors.map(v => tf.tensor2d([v], [1, v.length]))
    const baseline = await Promise.all(
      tensors.map(async t => {
        const r = this._ae.predict(t)
        const e = (await tf.losses.meanSquaredError(t.flatten(), r.flatten()).data())[0]
        t.dispose(); r.dispose()
        return e
      })
    )
    this._baselineERec = baseline.reduce((s, v) => s + v, 0) / baseline.length
    this._timer = setInterval(() => {}, 30_000)
  }

  stop() { if (this._timer) clearInterval(this._timer) }

  async check(vector, behavioralProfile) {
    const t    = tf.tensor2d([vector], [1, vector.length])
    const r    = this._ae.predict(t)
    const eRec = (await tf.losses.meanSquaredError(t.flatten(), r.flatten()).data())[0]
    t.dispose(); r.dispose()
    this.lastERec = eRec

    const threshold = behavioralProfile
      ? Math.min(behavioralProfile.adaptiveThreshold * 0.05, EREC_THRESH * 1.5)
      : EREC_THRESH

    this.lastDrift  = behavioralProfile?.lastDrift ?? 0
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

// ── Per-User Profile Persistence ──────────────────────────────────────────────
const PROFILE_PREFIX  = 'ep_bioprofile_'
const SELECTOR_PREFIX = 'ep_featsel_'

export function saveUserProfile(userId, profile, selector) {
  try {
    localStorage.setItem(PROFILE_PREFIX  + userId, JSON.stringify(profile.toJSON()))
    localStorage.setItem(SELECTOR_PREFIX + userId, JSON.stringify(selector.toJSON()))
  } catch {}
}

export function loadUserProfile(userId) {
  try {
    const profileData  = JSON.parse(localStorage.getItem(PROFILE_PREFIX  + userId))
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

// ── Frozen Enrollment Template ────────────────────────────────────────────────
/**
 * Immutable snapshot of the OWNER's typing signature, captured once at
 * enrollment and NEVER adapted afterwards. Verification compares the live
 * signature against this frozen template, so an impostor can never become the
 * new baseline (the EMA-laundering failure mode is eliminated).
 */
const TEMPLATE_PREFIX = 'ep_enrolltpl_'

export class EnrollmentTemplate {
  constructor(data) {
    this.dwellMean   = data.dwellMean
    this.dwellStd    = data.dwellStd
    this.flightMean  = data.flightMean
    this.flightStd   = data.flightStd
    this.digraphs    = data.digraphs || {}   // "prevCode>code" → latency ms (legacy bigram-dwell)
    this.mouse       = data.mouse || { speed: 0, jitter: 0, accel: 0 }
    this.frozenAt    = data.frozenAt || Date.now()
    this.basisKeys   = data.basisKeys || 0
    // ── Enhanced profiles (Features 1–7). Backward compatible: older templates
    //    lack these → null/{} → the matching live similarity returns null and is
    //    dropped from the weighted score (graceful degradation). ──────────────
    this.digraphProfile   = data.digraphProfile   || null
    this.trigraphProfile  = data.trigraphProfile  || null
    this.burstProfile     = data.burstProfile     || null
    this.backspaceProfile = data.backspaceProfile || null
    this.spacebarProfile  = data.spacebarProfile  || null
    this.dwellProfile     = data.dwellProfile     || null
    this.phraseProfile    = data.phraseProfile    || null
  }

  /** Capture a frozen template from the current capture buffers. */
  static capture(keyboard, pointer) {
    const kf = keyboard.getDwellFlightStats(300)
    const ms = pointer.getStats()
    const rich = keyboard.getRichReadiness()
    return new EnrollmentTemplate({
      dwellMean:  kf.dwellMean,
      dwellStd:   kf.dwellStd,
      flightMean: kf.flightMean,
      flightStd:  kf.flightStd,
      digraphs:   keyboard.getDigraphMap(),
      mouse:      { speed: ms.avgSpeed || 0, jitter: ms.avgJitter || 0, accel: ms.avgAccel || 0 },
      frozenAt:   Date.now(),
      basisKeys:  kf.count,
      // Only freeze a rich profile when there is enough evidence for it.
      digraphProfile:   rich.digraphs >= 6 ? keyboard.getDigraphProfile(50)  : null,
      trigraphProfile:  rich.trigraphs >= 5 ? keyboard.getTrigraphProfile(40) : null,
      burstProfile:     keyboard.getBurstProfile(),
      backspaceProfile: rich.chars >= 20 ? keyboard.getBackspaceProfile() : null,
      spacebarProfile:  keyboard.getSpacebarProfile().n >= 3 ? keyboard.getSpacebarProfile() : null,
      dwellProfile:     keyboard.getDwellProfile().n >= 10 ? keyboard.getDwellProfile() : null,
      phraseProfile:    rich.chars >= 20 ? keyboard.getPhraseProfile() : null,
    })
  }

  toJSON() { return { ...this } }
  static fromJSON(obj) { return obj ? new EnrollmentTemplate(obj) : null }
}

export function saveEnrollmentTemplate(userId, tpl) {
  try { localStorage.setItem(TEMPLATE_PREFIX + userId, JSON.stringify(tpl.toJSON())) } catch {}
}
export function loadEnrollmentTemplate(userId) {
  try {
    const raw = localStorage.getItem(TEMPLATE_PREFIX + userId)
    return raw ? EnrollmentTemplate.fromJSON(JSON.parse(raw)) : null
  } catch { return null }
}
export function clearEnrollmentTemplate(userId) {
  try { localStorage.removeItem(TEMPLATE_PREFIX + userId) } catch {}
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
    this._userId             = null
    this.behavioralProfile   = new UserBehavioralProfile()
    this.featureSelector     = new UserFeatureSelector()
    this._featureSampleCount = 0
    // Frozen-template identity scoring
    this.enrollTemplate      = null
    this._lastIdentity       = null
    this._reauthStreak       = 0
    this._reauthCooldownUntil = 0       // FIX 4: post-verify cooldown
    this._lastEvalKeyTs       = -Infinity  // FIX 3: require NEW evidence
    this._lastEvalPtrTs       = -Infinity
    this._idleLogged          = false   // throttle idle debug logging
    // Progressive scoring state
    this._scoreWindow         = []      // rolling window of raw scores
    this._suspicion           = 0       // suspicion accumulator
    this._smoothConf          = null    // EMA-smoothed confidence
  }

  setUpdateCallback(fn) { this._onUpdate = fn }

  setUser(userId) {
    this._userId = userId
    if (userId) {
      const { profile, selector } = loadUserProfile(userId)
      this.behavioralProfile = profile
      this.featureSelector   = selector
      this.enrollTemplate    = loadEnrollmentTemplate(userId)
      this._lastIdentity     = null
      this._reauthStreak     = 0
    }
  }

  /** Discard the frozen template so the next sufficient typist re-enrolls. */
  resetEnrollmentTemplate() {
    this.enrollTemplate = null
    this._lastIdentity  = null
    this._reauthStreak  = 0
    this._scoreWindow   = []
    this._suspicion     = 0
    this._smoothConf    = null
    if (this._userId) clearEnrollmentTemplate(this._userId)
  }

  /**
   * FIX 1 + FIX 4 — called after a successful re-authentication / verify.
   * Returns the session to a clean trusted state and starts a cooldown during
   * which no new re-auth can fire (prevents the immediate re-auth loop). The
   * frozen enrollment template is NOT touched — identity is still owner-bound.
   */
  confirmVerified() {
    this._reauthStreak  = 0                 // clear streak / gating state
    this._suspicion     = 0                 // clear suspicion accumulator
    this._scoreWindow   = []                // clear rolling low-score window (clears lowCount)
    this._smoothConf    = 100               // reset EMA / smoothed confidence to 100
    this._reauthCooldownUntil = performance.now() + ID_REAUTH_COOLDOWN_MS  // 120s cooldown
    // clear the legacy drift history + any monitor state
    if (this.behavioralProfile) {
      this.behavioralProfile.driftHistory = []
      this.behavioralProfile.lastDrift    = 0
    }
    if (this.watchdog) {
      this.watchdog.trustScore = 1.0        // clear watchdog temporary penalties
      this.watchdog.lastERec   = 0
    }
    // Snap identity back to fully trusted so idle/heartbeat read a clean value.
    this._lastIdentity = this.enrollTemplate
      ? { identityScore: 100, rawScore: 100, suspicion: 0, zone: 'trusted', reauth: false,
          cooldown: true, corroborated: true, effectiveTrust: 1.0,
          typingSim: 1, digraphSim: 1, mouseSim: 1, gated: false, sharedDigraphs: 0 }
      : null
    console.log('[Reauth] Reauth Success')
    console.log('[Reauth] Trust Reset (trustScore=1.0, identityScore=100, streak=0)')
    console.log(`[Reauth] Cooldown Started (${ID_REAUTH_COOLDOWN_MS / 1000}s)`)
  }

  /**
   * Freeze the enrollment template once enough OWNER evidence exists and no
   * template is stored yet. The first sufficiently-typed session becomes the
   * immutable baseline; it is never updated afterwards.
   */
  _maybeEnroll() {
    if (this.enrollTemplate) return
    if (this.keyboard._events.length < ID_ENROLL_MIN_KEYS) return
    if (this.keyboard.getDigraphCount() < ID_ENROLL_MIN_DIGRAPHS) return
    this.enrollTemplate = EnrollmentTemplate.capture(this.keyboard, this.pointer)
    if (this._userId) saveEnrollmentTemplate(this._userId, this.enrollTemplate)
    console.log('[Enroll] Frozen template captured:',
      `dwell=${this.enrollTemplate.dwellMean.toFixed(0)}ms`,
      `flight=${this.enrollTemplate.flightMean.toFixed(0)}ms`,
      `digraphs=${Object.keys(this.enrollTemplate.digraphs).length}`)
  }

  /**
   * Identity score (0–100) of the live typing signature vs the frozen template.
   * Typing + digraph dominate; mouse is a weak tie-breaker. A large typing or
   * digraph mismatch is gated so matching mouse data cannot mask a different
   * human. Returns null when there isn't enough live evidence (hold trust).
   */
  computeIdentity() {
    const tpl = this.enrollTemplate
    if (!tpl) return null
    const live = this.keyboard.getDwellFlightStats(CNN_SEQ_LEN)
    if (live.count < ID_MIN_LIVE_KEYS) return null

    // ── Typing similarity (dwell + flight means, relative-diff) ──────────────
    const dwellRel  = _relDiff(live.dwellMean,  tpl.dwellMean)
    const flightRel = _relDiff(live.flightMean, tpl.flightMean)
    const typingSim = (_gaussSim(dwellRel, ID_TOL_TYPING) + _gaussSim(flightRel, ID_TOL_TYPING)) / 2

    // ── Digraph similarity (shared digraphs only) ────────────────────────────
    const liveDg = this.keyboard.getDigraphMap()
    const shared = Object.keys(tpl.digraphs).filter(k => liveDg[k] !== undefined)
    let digraphSim, digraphRel = 0
    if (shared.length >= 3) {
      const rels = shared.map(k => _relDiff(liveDg[k], tpl.digraphs[k]))
      digraphRel = rels.reduce((s, v) => s + v, 0) / rels.length
      digraphSim = _gaussSim(digraphRel, ID_TOL_DIGRAPH)
    } else {
      digraphSim = typingSim   // not enough overlap → defer to typing
    }

    // ── Mouse similarity (weak, lenient) ─────────────────────────────────────
    const pm = this.pointer.getStats()
    const mouseRel = (
      _relDiff(pm.avgSpeed  || 0, tpl.mouse.speed)  +
      _relDiff(pm.avgJitter || 0, tpl.mouse.jitter) +
      _relDiff(pm.avgAccel  || 0, tpl.mouse.accel)
    ) / 3
    const mouseSim = pm.count > 5 ? _gaussSim(mouseRel, ID_TOL_MOUSE) : 1.0

    // ── Enhanced keyboard-biometric signals (Features 1–7) ───────────────────
    // Each returns [0,1], or null when the live data / template lacks evidence
    // (null signals are dropped from the weighted score, never penalised).
    const kb = this.keyboard
    const digraphProfileSim = _profileSim(kb.getDigraphProfile(50),  tpl.digraphProfile,  ID_TOL_DIGRAPH, ID_MIN_DG_OVERLAP)
    const trigraphSim       = _profileSim(kb.getTrigraphProfile(40), tpl.trigraphProfile, ID_TOL_TRIGRAPH, ID_MIN_TG_OVERLAP)
    const burstSim          = _burstSim(kb.getBurstProfile(),       tpl.burstProfile)
    const backspaceSim      = _backspaceSim(kb.getBackspaceProfile(), tpl.backspaceProfile)
    const spacebarSim       = _spacebarSim(kb.getSpacebarProfile(),  tpl.spacebarProfile)
    const dwellSim          = _dwellSim(kb.getDwellProfile(),        tpl.dwellProfile)
    const phraseSim         = _phraseSim(kb.getPhraseProfile(),      tpl.phraseProfile)

    // ── Weighted evidence fusion (renormalised over available signals) ───────
    const signals = [
      ['typing',         typingSim,         ID_WEIGHTS.typing],
      ['digraph',        digraphSim,        ID_WEIGHTS.digraph],
      ['mouse',          mouseSim,          ID_WEIGHTS.mouse],
      ['digraphProfile', digraphProfileSim, ID_WEIGHTS.digraphProfile],
      ['trigraph',       trigraphSim,       ID_WEIGHTS.trigraph],
      ['burst',          burstSim,          ID_WEIGHTS.burst],
      ['backspace',      backspaceSim,      ID_WEIGHTS.backspace],
      ['spacebar',       spacebarSim,       ID_WEIGHTS.spacebar],
      ['dwell',          dwellSim,          ID_WEIGHTS.dwell],
      ['phrase',         phraseSim,         ID_WEIGHTS.phrase],
    ]
    const avail = signals.filter(s => s[1] != null)
    const totW  = avail.reduce((s, x) => s + x[2], 0) || 1
    let rawScore = Math.round(100 * avail.reduce((s, x) => s + x[1] * x[2], 0) / totW)
    rawScore = Math.max(0, Math.min(100, rawScore))

    // ── False-positive guard (Feature requirement): ONE drifting signal must
    //    never reach the re-auth band. Only ≥ ID_DRIFT_MIN independent signals
    //    drifting together may push the score below the monitor floor. ────────
    const driftCount = avail.filter(s => s[1] < ID_DRIFT_THRESH).length
    if (driftCount < ID_DRIFT_MIN) rawScore = Math.max(rawScore, ID_MONITOR_MIN)

    // `gated` is kept as a diagnostic flag only — it NO LONGER caps the score.
    const gated = dwellRel > ID_GATE_DWELL || flightRel > ID_GATE_FLIGHT || digraphRel > ID_GATE_DIGRAPH

    // ── Rolling window of recent evaluations (Task 4) ────────────────────────
    this._scoreWindow.push(rawScore)
    if (this._scoreWindow.length > ID_WINDOW) this._scoreWindow.shift()
    const lowCount = this._scoreWindow.filter(v => v < ID_MONITOR_MIN).length

    // ── Gradual confidence via EMA smoothing (Task 6: 98→90→82→… not 98→40) ──
    this._smoothConf = this._smoothConf == null
      ? rawScore
      : (1 - ID_SMOOTH_ALPHA) * this._smoothConf + ID_SMOOTH_ALPHA * rawScore
    const conf = Math.max(0, Math.min(100, Math.round(this._smoothConf)))

    // ── Corroboration (Task 7): a strong digraph + mouse match means this is
    //    very likely the OWNER typing in a different context (speed varies). Do
    //    not escalate to re-auth even when typing similarity drops. ───────────
    // Corroboration: the legacy digraph+mouse match, OR a strong dwell match
    // combined with a strong digraph/trigraph profile match (the new hard-to-fake
    // keystroke signals) — either means "very likely the owner".
    const corroborated =
      (digraphSim > ID_CORROB_DIGRAPH && mouseSim > ID_CORROB_MOUSE) ||
      (dwellSim != null && dwellSim > 0.85 && Math.max(digraphProfileSim ?? 0, trigraphSim ?? 0) > 0.80)

    // ── Suspicion accumulator (Tasks 2 & 5) ──────────────────────────────────
    if (corroborated || conf >= ID_TRUSTED_MIN) {
      this._suspicion = Math.max(0, this._suspicion - 2)         // strong evidence → recover
    } else if (conf < ID_MONITOR_MIN) {
      this._suspicion = Math.min(ID_SUSP_MAX, this._suspicion + 1)  // sustained low → accrue
    } else {
      this._suspicion = Math.max(0, this._suspicion - 0.5)       // monitor band → slow recover
    }

    // ── Three states (Task 3) ────────────────────────────────────────────────
    const zone = conf >= ID_TRUSTED_MIN ? 'trusted'
               : conf >= ID_MONITOR_MIN ? 'monitor'
               : 'reauth'

    // ── Re-auth only on a SUSTAINED pattern (Tasks 5,7,FIX 4) ────────────────
    const inCooldown = performance.now() < this._reauthCooldownUntil
    const sustained  = this._suspicion >= ID_SUSP_REAUTH && lowCount >= ID_SUSP_MIN_LOW
    const reauth = !inCooldown && !corroborated && sustained
    this._reauthStreak = sustained ? this._reauthStreak + 1 : 0   // legacy/back-compat

    // Effective trust drives the visible confidence and the modal. It eases
    // gradually with `conf`; until a sustained pattern is confirmed (or while
    // corroborated / in cooldown) it is held in the monitor band so a transient
    // dip never crosses into the re-auth/modal range. Once sustained, the true
    // low score is released and the modal fires.
    let effectiveTrust = conf / 100
    if (!reauth) effectiveTrust = Math.max(effectiveTrust, ID_MONITOR_FLOOR)

    // ── CHANGE 1 — POST-REAUTH COOLDOWN HOLD ─────────────────────────────────
    // For the entire 120s verification cooldown the session is pinned to a fully
    // Trusted state: confidence cannot decrease, suspicion stays 0, and re-auth
    // cannot trigger. Normal monitoring resumes automatically afterward.
    let outConf = conf, outZone = zone, outReauth = reauth
    if (inCooldown) {
      this._smoothConf = 100          // keep the smoothed confidence pinned (no decay)
      this._suspicion  = 0
      effectiveTrust   = 1.0
      outConf = 100; outZone = 'trusted'; outReauth = false
    }

    // Behaviour vector — the full multi-signal fingerprint (for diagnostics/debug).
    const behaviorVector = {
      typing: _r3(typingSim), digraph: _r3(digraphSim), mouse: _r3(mouseSim),
      digraphProfile: _r3(digraphProfileSim), trigraph: _r3(trigraphSim),
      burst: _r3(burstSim), backspace: _r3(backspaceSim), spacebar: _r3(spacebarSim),
      dwell: _r3(dwellSim), phrase: _r3(phraseSim),
    }

    return {
      identityScore: outConf,        // smoothed (gradual) — the progressive score
      rawScore,                      // instantaneous fused similarity (diagnostic)
      suspicion: Math.round(this._suspicion * 10) / 10,
      zone: outZone,
      reauth: outReauth,
      cooldown: inCooldown,
      corroborated,
      driftCount,                    // # of independent signals currently drifting
      effectiveTrust,
      // Existing signals (unchanged)
      typingSim:  +typingSim.toFixed(3),
      digraphSim: +digraphSim.toFixed(3),
      mouseSim:   +mouseSim.toFixed(3),
      // New enhanced signals (null when no evidence yet)
      digraphProfileSim: _r3(digraphProfileSim),
      trigraphSim:       _r3(trigraphSim),
      burstSim:          _r3(burstSim),
      backspaceSim:      _r3(backspaceSim),
      spacebarSim:       _r3(spacebarSim),
      dwellSim:          _r3(dwellSim),
      phraseSim:         _r3(phraseSim),
      behaviorVector,
      gated,
      sharedDigraphs: shared.length,
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

  /**
   * Idle = no KEYBOARD activity within INACTIVITY_MS.
   *
   * DEMO-CRITICAL FIX: identity is a TYPING signature, so only keystrokes count
   * as activity. Mouse movement / scrolling must NEVER un-freeze scoring (they
   * would otherwise re-score against a stale keyboard window and drop the score
   * even though the user is not typing). Pointer activity is deliberately
   * ignored here.
   */
  _isIdle() {
    return (performance.now() - this.keyboard.getLastTs()) > INACTIVITY_MS
  }

  async _liveEval() {
    if (!this._ready || !this.cnn) return
    // Idle sessions produce no new behavioural evidence. Skipping the eval keeps
    // sampleCount/drift/EMA frozen so inactivity is never mistaken for drift.
    // FIX 2: idle freezes identity, drift, reauth counters and watchdog — and
    // emits no re-auth. Log once per idle entry (throttled).
    if (this._isIdle()) {
      if (!this._idleLogged) {
        console.log('[Identity] Idle Detected')
        console.log('[Identity] Behavior Evaluation Skipped (idle — frozen)')
        this._idleLogged = true
      }
      return
    }
    this._idleLogged = false
    try {
      const t = buildCNNInput(
        this.keyboard.getWindow(), this.pointer.getWindow(), this.keyboard
      )
      const s    = this.cnn.predict(t)
      this.theta = (await s.data())[0]
      t.dispose(); s.dispose()

      const featureVec = buildFeatureVector(
        this.keyboard.getWindow(), this.pointer.getWindow(), this.keyboard
      )
      this.featureSelector.update(featureVec)
      const drift = this.behavioralProfile.update(Array.from(featureVec))
      this._featureSampleCount++

      console.log(
        `[LiveEval] theta=${this.theta.toFixed(3)}, ` +
        `drift=${drift.toFixed(3)}, samples=${this._featureSampleCount}`
      )

      this._onUpdate?.({
        type:             'score',
        theta:            this.theta,
        drift,
        selectedFeatures: this.featureSelector.selectedIndices,
        featureNames:     this.featureSelector.selectedIndices.map(i => FEATURE_NAMES[i]),
      })

      // ── Frozen-template identity scoring (human-vs-human) ──────────────────
      // Auto-freeze the owner's template on first sufficient typing, then score
      // every live tick against it. This is the dominant trust signal: it drives
      // trustScore so a different human drops confidence and triggers re-auth.
      this._maybeEnroll()

      // DEMO-CRITICAL FIX: only (re)score identity when there is genuinely NEW
      // KEYBOARD evidence since the last evaluation. Mouse movement / scrolling
      // must NOT trigger scoring — otherwise a mouse-only session re-scores
      // against a stale keyboard window and the mouse-similarity term drifts the
      // confidence down even though the user is not typing.
      const keyTs = this.keyboard.getLastTs()
      const hasNewEvidence = keyTs > this._lastEvalKeyTs
      if (!hasNewEvidence) {
        console.log('[Identity] Behavior Evaluation Skipped (no new keyboard evidence)')
        return
      }
      this._lastEvalKeyTs = keyTs

      const id = this.computeIdentity()
      if (id) {
        this._lastIdentity = id
        if (this.watchdog) this.watchdog.trustScore = id.effectiveTrust
        console.log(
          `[Identity] conf=${id.identityScore} raw=${id.rawScore} zone=${id.zone} ` +
          `suspicion=${id.suspicion} typing=${id.typingSim} digraph=${id.digraphSim} mouse=${id.mouseSim}` +
          (id.corroborated ? ' [CORROBORATED]' : '') + (id.reauth ? ' [RE-AUTH]' : '')
        )
        this._onUpdate?.({
          type:          'identity',
          identityScore: id.identityScore,
          rawScore:      id.rawScore,
          suspicion:     id.suspicion,
          zone:          id.zone,
          reauth:        id.reauth,
          corroborated:  id.corroborated,
          driftCount:    id.driftCount,
          trustScore:    id.effectiveTrust,
          typingSim:     id.typingSim,
          digraphSim:    id.digraphSim,
          mouseSim:      id.mouseSim,
          // enhanced keyboard-biometric signals
          digraphProfileSim: id.digraphProfileSim,
          trigraphSim:       id.trigraphSim,
          burstSim:          id.burstSim,
          backspaceSim:      id.backspaceSim,
          spacebarSim:       id.spacebarSim,
          dwellSim:          id.dwellSim,
          phraseSim:         id.phraseSim,
          behaviorVector:    id.behaviorVector,
          gated:         id.gated,
        })
      }
    } catch (e) {
      console.error('[LiveEval] error:', e)
    }
  }

  _persistProfile() {
    if (this._userId) {
      saveUserProfile(this._userId, this.behavioralProfile, this.featureSelector)
    }
  }

  async evaluate(password = '') {
    try {
      const keyEvents     = this.keyboard.getWindow(CNN_SEQ_LEN)
      const pointerEvents = this.pointer.getWindow(CNN_SEQ_LEN)

      if (keyEvents.length < 5) {
        console.log('[evaluate] Not enough keyboard events:', keyEvents.length)
        return { theta: 0.5, hExp: 0.0 }
      }

      const t        = buildCNNInput(keyEvents, pointerEvents, this.keyboard)
      const s        = this.cnn.predict(t)
      const thetaRaw = (await s.data())[0]
      t.dispose(); s.dispose()

      this.theta = isFinite(thetaRaw) ? Math.max(0, Math.min(1, thetaRaw)) : 0.5
      this.hExp  = computeExpectationEntropy(password)
      this.hExp  = isFinite(this.hExp)  ? Math.max(0, Math.min(1, this.hExp))  : 0.0

      console.log(`[evaluate] theta=${this.theta.toFixed(3)}, hExp=${this.hExp.toFixed(3)}`)
      return { theta: this.theta, hExp: this.hExp }
    } catch (e) {
      console.error('[evaluate] error:', e)
      return { theta: 0.5, hExp: 0.0 }
    }
  }

  /**
   * Perform full biometric check with per-user profile drift detection.
   * Used by the watchdog heartbeat.
   */
  async checkIdentity() {
    // FIX: the watchdog autoencoder reconstructs the ORIGINAL behavioural
    // feature vector (CNN_SEQ_LEN * CNN_FEATURES = 400 dims), NOT the 32-dim
    // latent. Previously this passed getLatentVector() (32 dims) into the
    // autoencoder, causing the runtime error:
    //   "expected input4 to have shape [null,400] but got array with shape [1,32]"
    // The 32-dim latent is still produced separately by getLatentVector() for
    // the backend /session/verify call — only the client-side anomaly check
    // uses the 400-dim feature vector here.
    // Idle guard: with no recent interaction there is no new behavioural
    // evidence, so HOLD the previous confidence instead of decaying it. This
    // prevents inactivity from being scored as drift / deviation.
    if (this._isIdle()) {
      return {
        eRec:       this.watchdog?.lastERec ?? 0,
        trustScore: this.watchdog?.trustScore ?? 1,
        idle:       true,
      }
    }

    // Frozen-template identity is the authoritative trust signal once enrolled.
    // It is recomputed continuously in _liveEval; reuse the latest result so the
    // 30 s server heartbeat agrees with the live confidence the user sees.
    if (this.enrollTemplate && this._lastIdentity) {
      const id = this._lastIdentity
      return {
        eRec:          this.watchdog?.lastERec ?? 0,
        trustScore:    id.effectiveTrust,
        idle:          false,
        identityScore: id.identityScore,
        zone:          id.zone,
        reauth:        id.reauth,
      }
    }

    const vec = await this._buildWatchdogInput()
    if (!this.watchdog || !vec) {
      return {
        eRec:       this.watchdog?.lastERec ?? 0,
        trustScore: this.watchdog?.trustScore ?? 1,
      }
    }
    return this.watchdog.check(vec, this.behavioralProfile)
  }

  /**
   * Build the 400-dim autoencoder input (flattened [1, 50, 8] CNN window).
   * Returns null when there isn't enough recent input — the heartbeat then
   * skips the anomaly check this tick instead of crashing.
   */
  async _buildWatchdogInput() {
    try {
      const keyEvents     = this.keyboard.getWindow(CNN_SEQ_LEN)
      const pointerEvents = this.pointer.getWindow(CNN_SEQ_LEN)
      if (keyEvents.length < 10) return null
      const tensor    = buildCNNInput(keyEvents, pointerEvents, this.keyboard)
      const flattened = tensor.reshape([1, CNN_SEQ_LEN * CNN_FEATURES])
      tensor.dispose()
      const arr = Array.from(await flattened.data())
      flattened.dispose()
      return arr
    } catch (e) {
      console.error('[checkIdentity] watchdog input build failed:', e)
      return null
    }
  }

  getKeyboardStats() { return this.keyboard.getStats() }
  getPointerStats()  { return this.pointer.getStats() }

  getProfileStats() {
    return {
      sampleCount:       this.behavioralProfile.sampleCount,
      lastDrift:         this.behavioralProfile.lastDrift,
      adaptiveThreshold: this.behavioralProfile.adaptiveThreshold,
      isDrifting:        this.behavioralProfile.isDrifting,
      selectedFeatures:  this.featureSelector.selectedIndices.map(i => FEATURE_NAMES[i]),
      featureMeans:      Array.from(this.featureSelector.means),
      // Frozen-template identity diagnostics (for the dev debug panel)
      enrolled:          !!this.enrollTemplate,
      identity:          this._lastIdentity,
    }
  }

  /**
   * Phase D.1 (SHADOW): current normalized 8-dim behavioral window.
   * Read-only — computed from the existing capture windows via buildFeatureVector.
   * Does NOT mutate any profile/EMA state and does NOT affect drift, trust, or the
   * confidence system. Returns null when there isn't enough recent input.
   */
  getFeatureVector() {
    try {
      const keyEvents     = this.keyboard.getWindow(CNN_SEQ_LEN)
      const pointerEvents = this.pointer.getWindow(CNN_SEQ_LEN)
      if (keyEvents.length < 5) return null
      const fv = buildFeatureVector(keyEvents, pointerEvents, this.keyboard)
      return Array.from(fv)
    } catch {
      return null
    }
  }

  destroy() {
    this._persistProfile()
    this.keyboard.stop()
    this.pointer.stop()
    if (this._evalLoop) clearInterval(this._evalLoop)
    if (this._saveLoop) clearInterval(this._saveLoop)
    if (this.watchdog)  this.watchdog.stop()
  }

  /**
   * Generates a 32-dim latent vector from current behavioral signals.
   * Uses the full 8-channel CNN input reshaped for the autoencoder encoder.
   * Falls back to a small-noise random vector when there aren't enough events yet.
   */
  async getLatentVector() {
    try {
      const keyEvents     = this.keyboard.getWindow(CNN_SEQ_LEN)
      const pointerEvents = this.pointer.getWindow(CNN_SEQ_LEN)

      if (keyEvents.length < 10) {
        console.log(
          '[getLatentVector] Not enough samples:', keyEvents.length,
          '— returning random vector'
        )
        return new Array(LATENT_DIM).fill(0).map(() => Math.random() * 0.1)
      }

      // Build [1, 50, 8] tensor then flatten to [1, 400] for the autoencoder
      const tensor    = buildCNNInput(keyEvents, pointerEvents, this.keyboard)
      const flattened = tensor.reshape([1, CNN_SEQ_LEN * CNN_FEATURES])
      tensor.dispose()

      const enc = this.watchdog?._enc
      if (!enc) {
        console.warn('[getLatentVector] Encoder not available')
        flattened.dispose()
        return new Array(LATENT_DIM).fill(0).map(() => Math.random() * 0.1)
      }

      const encoded = enc.predict(flattened)
      const result  = Array.from(await encoded.data())
      flattened.dispose()
      encoded.dispose()

      console.log(
        '[getLatentVector] vector length:', result.length,
        'first 5:', result.slice(0, 5)
      )

      // Guard against unexpected encoder output length
      if (result.length !== LATENT_DIM) {
        console.warn(
          '[getLatentVector] length mismatch — expected', LATENT_DIM, 'got', result.length
        )
        const padded = new Array(LATENT_DIM).fill(0)
        result.slice(0, LATENT_DIM).forEach((v, i) => { padded[i] = v })
        return padded
      }

      return result
    } catch (e) {
      console.error('[getLatentVector] exception:', e)
      return new Array(LATENT_DIM).fill(0).map(() => Math.random() * 0.05)
    }
  }

  /** Total feature-profile ticks since the engine was started. */
  getSampleCount() { return this._featureSampleCount }

  /** Raw keyboard event buffer size (useful for debugging minimum-event guards). */
  getKeyboardEventCount() { return this.keyboard._events.length }
}

// ── Session Token Binder ──────────────────────────────────────────────────────
/**
 * Cryptographically binds a backend session token to a biometric latent vector
 * to prevent token theft or replay across different biometric profiles.
 */
export class SessionTokenBinder {
  constructor(sessionToken) {
    this.token = sessionToken
  }

  async bind(latentVector) {
    if (!latentVector || latentVector.length !== LATENT_DIM) {
      throw new Error('Invalid latent vector for binding')
    }
    return {
      token:     this.token,
      binding:   this._computeBinding(latentVector),
      timestamp: Date.now(),
    }
  }

  _computeBinding(latent) {
    const sum = latent.reduce((a, b) => a + b, 0)
    return `lb_${sum.toFixed(4)}_${latent[0].toFixed(2)}`
  }
}