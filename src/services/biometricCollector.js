/**
 * BiometricCollector Service
 * ===========================
 * Single source of truth for biometric sample collection progress.
 *
 * Design contract:
 *  - addSample()          → accumulates raw keystroke metrics in-memory
 *  - aggregatePattern()   → converts buffer → pattern (local only, not persisted)
 *  - markPersisted(n)     → called by ProfileBuildPage ONLY after a successful
 *                           backend syncBiometricProfile() response; increments
 *                           persistedSamples so the UI can distinguish "collected"
 *                           from "actually saved to backend"
 *  - getState()           → { collectedSamples, persistedSamples, isStable, ... }
 *
 * The UI must never show a sample as "stable" until persistedSamples >= targetSamples.
 */

export class BiometricCollector {
  constructor(options = {}) {
    this.minSamplesPerPattern = options.minSamplesPerPattern || 15
    this.targetSamples        = options.targetSamples        || 50
    this.debounceMs           = options.debounceMs           || 1500

    // In-memory buffer of raw samples not yet aggregated into a pattern
    this._pendingSamples = []
    // Aggregated patterns (local, may or may not be persisted yet)
    this._patterns = []
    // Total samples that have been aggregated into patterns (local)
    this.collectedSamples = 0
    // Samples confirmed written to the backend (set via markPersisted)
    this.persistedSamples = 0

    this.debounceTimer = null
  }

  // ── Sample ingestion ─────────────────────────────────────────────────────

  /**
   * Add a single biometric sample.
   * Auto-aggregates into a pattern once minSamplesPerPattern is reached.
   * Returns current state snapshot.
   */
  addSample(sample) {
    if (!sample || typeof sample !== 'object') return this.getState()

    this._pendingSamples.push({ timestamp: Date.now(), ...sample })

    if (this._pendingSamples.length >= this.minSamplesPerPattern) {
      this.aggregatePattern()
    }

    return this.getState()
  }

  /**
   * Flush pending samples into a pattern regardless of buffer size.
   * Called before a sync to ensure nothing is left in the buffer.
   */
  flushPending() {
    if (this._pendingSamples.length >= 3) {
      this.aggregatePattern()
    }
  }

  /**
   * Aggregate current pending buffer into a stored pattern.
   */
  aggregatePattern() {
    if (this._pendingSamples.length === 0) return null

    const pattern = {
      patternId:    `pattern_${Date.now()}_${this._patterns.length}`,
      sampleCount:  this._pendingSamples.length,
      aggregatedAt: Date.now(),
      stats:        this._computeStatsFromSamples(this._pendingSamples),
      // Keep a shallow copy for later analysis; trim to avoid memory bloat
      samples:      this._pendingSamples.slice(-20),
    }

    this._patterns.push(pattern)
    this.collectedSamples += this._pendingSamples.length
    this._pendingSamples = []

    console.log(
      `[BiometricCollector] Pattern aggregated: ${pattern.sampleCount} samples | ` +
      `collected=${this.collectedSamples} persisted=${this.persistedSamples}/${this.targetSamples}`
    )

    return pattern
  }

  // ── Persistence tracking ─────────────────────────────────────────────────

  /**
   * Called by ProfileBuildPage AFTER a successful syncBiometricProfile() API call.
   * n = number of new samples that were included in that sync payload.
   */
  markPersisted(n) {
    if (typeof n !== 'number' || n <= 0) return
    this.persistedSamples = Math.min(this.persistedSamples + n, this.collectedSamples)
    console.log(
      `[BiometricCollector] markPersisted(${n}) → persistedSamples=${this.persistedSamples}/${this.targetSamples}`
    )
  }

  // ── State ────────────────────────────────────────────────────────────────

  /**
   * Returns a snapshot of collection state for the UI.
   * isStable is ONLY true once persistedSamples >= targetSamples.
   */
  getState() {
    const isStable = this.persistedSamples >= this.targetSamples
    return {
      collectedSamples: this.collectedSamples,
      persistedSamples: this.persistedSamples,
      targetSamples:    this.targetSamples,
      patternCount:     this._patterns.length,
      pendingSamples:   this._pendingSamples.length,
      isStable,
      // Progress based on persisted (confirmed) samples only
      progress:         Math.min(this.persistedSamples / this.targetSamples, 1),
      lastPattern:      this._patterns[this._patterns.length - 1] || null,
      stats:            this._computeAllStats(),
    }
  }

  // ── Payload building ─────────────────────────────────────────────────────

  /**
   * Build the payload for syncBiometricProfile().
   * Also returns samplesInPayload so the caller knows how many to markPersisted.
   */
  buildSyncPayload(theta, hExp, latentVector, engineProfileStats) {
    // Flush any pending samples into the last pattern first
    this.flushPending()

    const stats            = this._computeAllStats()
    const samplesInPayload = this.collectedSamples - this.persistedSamples

    return {
      payload: {
        theta,
        h_exp:         hExp,
        latent_vector: latentVector ?? [],
        keyboard_stats: {
          avgDwell:  stats.avgDwell,
          avgFlight: stats.avgFlight,
          rhythm:    stats.rhythm,
          avgPause:  stats.pauseFreq,
        },
        pointer_stats: {
          avgSpeed:  stats.avgSpeed,
          avgJitter: stats.avgJitter,
          avgAccel:  stats.avgAccel,
        },
        profile_stats: {
          sampleCount:      this.collectedSamples,
          persistedSamples: this.persistedSamples,
          patternCount:     this._patterns.length,
          selectedFeatures: engineProfileStats?.selectedFeatures || [],
          featureMeans:     engineProfileStats?.featureMeans     || [],
          emaProfile:       engineProfileStats?.emaProfile,
          emaVariance:      engineProfileStats?.emaVariance,
        },
      },
      samplesInPayload: Math.max(samplesInPayload, 0),
    }
  }

  // ── Internals ────────────────────────────────────────────────────────────

  _computeStatsFromSamples(samples) {
    if (!samples.length) return this._zeroStats()
    const extract = key => samples.map(s => s[key] || 0).filter(v => v > 0)
    const avg     = vals => vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
    return {
      avgDwell:  avg(extract('dwell')),
      avgFlight: avg(extract('flight')),
      avgSpeed:  avg(extract('speed')),
      avgJitter: avg(extract('jitter')),
      avgAccel:  avg(extract('accel')),
      rhythm:    avg(extract('rhythm')),
      pauseFreq: avg(extract('pause')),
    }
  }

  _computeAllStats() {
    const allSamples = [
      ...this._patterns.flatMap(p => p.samples || []),
      ...this._pendingSamples,
    ]
    return allSamples.length ? this._computeStatsFromSamples(allSamples) : this._zeroStats()
  }

  _zeroStats() {
    return { avgDwell: 0, avgFlight: 0, avgSpeed: 0, avgJitter: 0, avgAccel: 0, rhythm: 0, pauseFreq: 0 }
  }

  // ── Lifecycle ────────────────────────────────────────────────────────────

  reset() {
    this._pendingSamples  = []
    this._patterns        = []
    this.collectedSamples = 0
    this.persistedSamples = 0
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
    this.debounceTimer = null
  }
}

// ── Singleton ────────────────────────────────────────────────────────────────

let _instance = null

export function getBiometricCollector(options) {
  if (!_instance) _instance = new BiometricCollector(options)
  return _instance
}

export function resetBiometricCollector() {
  if (_instance) _instance.reset()
  _instance = null
}