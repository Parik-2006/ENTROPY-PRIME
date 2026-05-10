/**
 * index.js — SDK Entry Point
 */

import { KeystrokeCollector, MouseCollector, TouchCollector } from './collectors';

const SDK_VERSION = '1.1.0';
const DEFAULT_ENDPOINT = 'http://localhost:8000/api/v1';

class BiometricSDK {
    constructor() {
        this.apiKey = this._getApiKey();
        this.userId = 'anonymous';
        this.endpoint = DEFAULT_ENDPOINT;
        this.buffer = [];
        this.initialized = false;
        
        this.collectors = [
            new KeystrokeCollector(this._capture.bind(this)),
            new MouseCollector(this._capture.bind(this)),
            new TouchCollector(this._capture.bind(this))
        ];
    }

    /**
     * Initialize the SDK with user configuration.
     * @param {Object} config - Configuration options (userId, endpoint).
     */
    init(config = {}) {
        if (this.initialized) return;
        
        this.userId = config.userId || this.userId;
        this.endpoint = config.endpoint || this.endpoint;
        
        // Start all collectors
        this.collectors.forEach(c => c.start());
        
        // Periodic sync
        setInterval(() => this._flush(), 5000);
        
        this.initialized = true;
        console.log(`[Entropy] SDK v${SDK_VERSION} initialized.`);
    }

    /**
     * Extracts API key from the script tag.
     */
    _getApiKey() {
        const script = document.currentScript || document.querySelector('script[data-api-key]');
        return script ? script.getAttribute('data-api-key') : null;
    }

    /**
     * Internal method to push events to the buffer.
     */
    _capture(category, data) {
        this.buffer.push({
            cat: category,
            data: data,
            ts: Date.now()
        });
        
        // Auto-flush if buffer is getting large
        if (this.buffer.length > 50) this._flush();
    }

    /**
     * Transmit buffered events to the Entropy Prime backend.
     */
    async _flush() {
        if (this.buffer.length === 0 || !this.apiKey) return;

        const payload = {
            apiKey: this.apiKey,
            userId: this.userId,
            timestamp: Date.now(),
            events: this.buffer.splice(0, this.buffer.length)
        };

        try {
            const response = await fetch(`${this.endpoint}/telemetry`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                },
                body: JSON.stringify(payload),
                keepalive: true
            });

            if (response.status === 401) {
                console.error('[Entropy] Unauthorized: Invalid API Key.');
            }
        } catch (err) {
            console.debug('[Entropy] Telemetry sync failed', err);
        }
    }
}

// Instantiate and expose to global scope
const instance = new BiometricSDK();
window.Entropy = instance;

// Auto-init support via data attribute
if (document.currentScript && document.currentScript.hasAttribute('data-auto-init')) {
    instance.init();
}

export default instance;
