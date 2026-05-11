/**
 * BiometricCollector Service
 * ===========================
 * Manages biometric sample collection, pattern aggregation, and persistence.
 * 
 * Architecture:
 *  - Collects individual keystroke/pointer samples in real-time
 *  - Aggregates samples into patterns (min 10-20 samples = 1 pattern)
 *  - Syncs patterns to backend for storage in MongoDB
 *  - Tracks sample count towards 50-sample stability target
 *  - Provides progress updates and drift monitoring
 */

export class BiometricCollector {
  constructor(options = {}) {
    this.minSamplesPerPattern = options.minSamplesPerPattern || 15;
    this.targetSamples = options.targetSamples || 50;
    this.debounceMs = options.debounceMs || 1500;

    this.samples = [];
    this.patterns = [];
    this.totalSamples = 0;
    this.isStable = false;
    this.lastSyncTime = null;
    this.debounceTimer = null;
  }

  /**
   * Add a single biometric sample (keystroke or pointer event)
   */
  addSample(sample) {
    if (!sample || typeof sample !== 'object') return;

    const enrichedSample = {
      timestamp: Date.now(),
      ...sample,
    };

    this.samples.push(enrichedSample);
    
    // Auto-aggregate when we hit min samples
    if (this.samples.length >= this.minSamplesPerPattern) {
      this.aggregatePattern();
    }

    return {
      sampleCount: this.totalSamples,
      isStable: this.isStable,
      progress: this.totalSamples / this.targetSamples,
    };
  }

  /**
   * Aggregate current samples into a pattern and clear the sample buffer
   */
  aggregatePattern() {
    if (this.samples.length === 0) return null;

    const pattern = {
      patternId: `pattern_${Date.now()}`,
      sampleCount: this.samples.length,
      aggregatedAt: Date.now(),
      stats: this.computeStatistics(),
      samples: [...this.samples], // Keep last N for later analysis
    };

    this.patterns.push(pattern);
    this.totalSamples += this.samples.length;
    this.samples = []; // Clear buffer

    // Check stability
    this.isStable = this.totalSamples >= this.targetSamples;

    console.log(
      `[BiometricCollector] Pattern aggregated: ${pattern.sampleCount} samples, ` +
      `Total: ${this.totalSamples}/${this.targetSamples}, Stable: ${this.isStable}`
    );

    return pattern;
  }

  /**
   * Compute statistics from all collected patterns
   */
  computeStatistics() {
    const allSamples = this.patterns.flatMap(p => p.samples || []).concat(this.samples);
    
    if (allSamples.length === 0) {
      return {
        avgDwell: 0,
        avgFlight: 0,
        avgSpeed: 0,
        avgJitter: 0,
        avgAccel: 0,
        rhythm: 0,
      };
    }

    const extract = (key) => allSamples.map(s => s[key] || 0).filter(v => v > 0);

    const avg = (values) => values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;

    return {
      avgDwell: avg(extract('dwell')),
      avgFlight: avg(extract('flight')),
      avgSpeed: avg(extract('speed')),
      avgJitter: avg(extract('jitter')),
      avgAccel: avg(extract('accel')),
      rhythm: avg(extract('rhythm')),
      pauseFreq: avg(extract('pause')),
    };
  }

  /**
   * Get current collection state for UI display
   */
  getState() {
    return {
      sampleCount: this.totalSamples,
      patternCount: this.patterns.length,
      isStable: this.isStable,
      progress: this.totalSamples / this.targetSamples,
      pendingSamples: this.samples.length,
      lastPattern: this.patterns[this.patterns.length - 1] || null,
      stats: this.computeStatistics(),
    };
  }

  /**
   * Prepare payload for backend sync
   */
  getPersistencePayload(theta, hExp, latentVector, profileStats) {
    return {
      theta,
      h_exp: hExp,
      latent_vector: latentVector || [],
      keyboard_stats: {
        avgDwell: this.computeStatistics().avgDwell,
        avgFlight: this.computeStatistics().avgFlight,
        rhythm: this.computeStatistics().rhythm,
        avgPause: this.computeStatistics().pauseFreq,
      },
      pointer_stats: {
        avgSpeed: this.computeStatistics().avgSpeed,
        avgJitter: this.computeStatistics().avgJitter,
        avgAccel: this.computeStatistics().avgAccel,
      },
      profile_stats: {
        sampleCount: this.totalSamples,
        patternCount: this.patterns.length,
        selectedFeatures: profileStats?.selectedFeatures || [],
        featureMeans: profileStats?.featureMeans || [],
        emaProfile: profileStats?.emaProfile,
        emaVariance: profileStats?.emaVariance,
      },
    };
  }

  /**
   * Reset collector (logout, new profile, etc.)
   */
  reset() {
    this.samples = [];
    this.patterns = [];
    this.totalSamples = 0;
    this.isStable = false;
    if (this.debounceTimer) clearTimeout(this.debounceTimer);
  }

  /**
   * Get pending samples before they're aggregated
   */
  getPendingSamples() {
    return [...this.samples];
  }
}

/**
 * Create a singleton instance
 */
let collectorInstance = null;

export function getBiometricCollector(options) {
  if (!collectorInstance) {
    collectorInstance = new BiometricCollector(options);
  }
  return collectorInstance;
}

export function resetBiometricCollector() {
  if (collectorInstance) {
    collectorInstance.reset();
  }
  collectorInstance = null;
}
