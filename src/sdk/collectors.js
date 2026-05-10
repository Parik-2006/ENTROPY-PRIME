/**
 * collectors.js — Specialized biometric data collectors
 */

export class KeystrokeCollector {
    constructor(onCapture) {
        this.onCapture = onCapture;
        this.lastKeyTime = 0;
        this.handleKeyDown = this.handleKeyDown.bind(this);
        this.handleKeyUp = this.handleKeyUp.bind(this);
    }

    start() {
        window.addEventListener('keydown', this.handleKeyDown, true);
        window.addEventListener('keyup', this.handleKeyUp, true);
    }

    stop() {
        window.removeEventListener('keydown', this.handleKeyDown, true);
        window.removeEventListener('keyup', this.handleKeyUp, true);
    }

    handleKeyDown(e) {
        const now = performance.now();
        // Calculate flight time (time between previous key down and current key down)
        if (this.lastKeyTime > 0) {
            const flightTime = now - this.lastKeyTime;
            this.onCapture('keystroke', { type: 'flight', value: flightTime, key: e.key });
        }
        this.lastKeyTime = now;
    }

    handleKeyUp(e) {
        const now = performance.now();
        // Calculate dwell time (time key was pressed)
        if (this.lastKeyTime > 0) {
            const dwellTime = now - this.lastKeyTime;
            this.onCapture('keystroke', { type: 'dwell', value: dwellTime, key: e.key });
        }
    }
}

export class MouseCollector {
    constructor(onCapture) {
        this.onCapture = onCapture;
        this.lastPos = { x: 0, y: 0, t: 0 };
        this.handleMouseMove = this.handleMouseMove.bind(this);
    }

    start() {
        window.addEventListener('mousemove', this.handleMouseMove, true);
    }

    stop() {
        window.removeEventListener('mousemove', this.handleMouseMove, true);
    }

    handleMouseMove(e) {
        const now = performance.now();
        const dt = now - this.lastPos.t;
        if (dt > 50) { // ~20Hz sampling rate
            const dx = e.clientX - this.lastPos.x;
            const dy = e.clientY - this.lastPos.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const speed = dist / dt;
            
            this.onCapture('mouse', { 
                speed: speed,
                x: e.clientX,
                y: e.clientY,
                ts: now
            });
            
            this.lastPos = { x: e.clientX, y: e.clientY, t: now };
        }
    }
}

export class TouchCollector {
    constructor(onCapture) {
        this.onCapture = onCapture;
        this.lastPos = { x: 0, y: 0, t: 0 };
        this.handleTouchMove = this.handleTouchMove.bind(this);
    }

    start() {
        window.addEventListener('touchmove', this.handleTouchMove, true);
    }

    stop() {
        window.removeEventListener('touchmove', this.handleTouchMove, true);
    }

    handleTouchMove(e) {
        const now = performance.now();
        const touch = e.touches[0];
        const dt = now - this.lastPos.t;
        
        if (dt > 50) {
            const dx = touch.clientX - this.lastPos.x;
            const dy = touch.clientY - this.lastPos.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const speed = dist / dt;

            this.onCapture('touch', {
                speed: speed,
                x: touch.clientX,
                y: touch.clientY,
                ts: now
            });

            this.lastPos = { x: touch.clientX, y: touch.clientY, t: now };
        }
    }
}
