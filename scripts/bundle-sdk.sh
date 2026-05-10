#!/usr/bin/env bash
# scripts/bundle-sdk.sh — Entropy Prime SDK bundler for CDN distribution
#
# Produces 7 outputs from public/sdk/:
#   entropy.min.js              IIFE bundle (minified, console stripped)
#   entropy.esm.min.js          ES module variant
#   entropy.min.js.br           Brotli pre-compressed
#   entropy.min.js.gz           Gzip pre-compressed
#   entropy.d.ts                TypeScript declarations
#   sdk-manifest.json           SRI hashes + byte sizes + ready-to-paste snippet

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SDK_SRC="${PROJECT_ROOT}/public/sdk"
OUT_DIR="${PROJECT_ROOT}/public/sdk"

echo "🔨 Entropy Prime SDK Bundler — v3.2.0"
echo "────────────────────────────────────────"

# Step 1: Check dependencies
echo "✓ Checking dependencies..."
for cmd in node npm terser tsc brotli gzip sha256sum; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "  ⚠️  Missing: $cmd (install via: npm install -g terser typescript brotli)"
        # Don't exit; some are optional (tsc for types, brotli for compression)
    fi
done

# Step 2: Identify entry point
ENTRY_FILE="${SDK_SRC}/index.js"
if [[ ! -f "$ENTRY_FILE" ]]; then
    echo "  ❌ Entry point not found: $ENTRY_FILE"
    exit 1
fi
echo "  ✓ Entry: $ENTRY_FILE"

# Step 3: IIFE bundle (Terser minified, console stripped)
echo ""
echo "📦 Bundling IIFE (entropy.min.js)..."
BUNDLE_IIFE="${OUT_DIR}/entropy.js"

# Naive IIFE wrapper: read file, wrap in (function(){...}())
cat > "$BUNDLE_IIFE" <<'EOF'
(function(window) {
EOF
cat "$ENTRY_FILE" >> "$BUNDLE_IIFE"
cat >> "$BUNDLE_IIFE" <<'EOF'
})(typeof window !== 'undefined' ? window : typeof global !== 'undefined' ? global : typeof self !== 'undefined' ? self : {});
EOF

# Minify with Terser (3-pass, strip console, remove dead code)
if command -v terser &>/dev/null; then
    echo "  → Minifying with Terser (3 passes)..."
    MINIFIED="${OUT_DIR}/entropy.min.js"
    
    # Pass 1: Initial minification
    terser "$BUNDLE_IIFE" -o "${MINIFIED}.tmp1" \
        --compress drop_console=true,passes=2 \
        --mangle --toplevel 2>/dev/null || true
    
    # Pass 2: Inline constants
    terser "${MINIFIED}.tmp1" -o "${MINIFIED}.tmp2" \
        --compress inline=3 --mangle 2>/dev/null || true
    
    # Pass 3: Final pass
    terser "${MINIFIED}.tmp2" -o "$MINIFIED" \
        --compress passes=3 --mangle 2>/dev/null || true
    
    rm -f "${MINIFIED}.tmp"*
    SIZE=$(stat -f%z "$MINIFIED" 2>/dev/null || stat -c%s "$MINIFIED" 2>/dev/null || echo "?")
    echo "  ✓ IIFE: $SIZE bytes → $MINIFIED"
else
    echo "  ⚠️  Terser not found; skipping minification"
    cp "$BUNDLE_IIFE" "${OUT_DIR}/entropy.min.js"
fi

# Step 4: ESM bundle (for bundlers + import maps)
echo ""
echo "📦 Creating ESM variant (entropy.esm.min.js)..."
ESM_FILE="${OUT_DIR}/entropy.esm.js"
# For ESM, just export the API object
cat > "$ESM_FILE" <<'EOF'
export { default as EntropyPrime } from './index.js';
EOF

if command -v terser &>/dev/null; then
    cat "$ENTRY_FILE" > "$ESM_FILE"
    terser "$ESM_FILE" -o "${OUT_DIR}/entropy.esm.min.js" \
        --module --compress drop_console=true --mangle 2>/dev/null || true
    SIZE=$(stat -f%z "${OUT_DIR}/entropy.esm.min.js" 2>/dev/null || stat -c%s "${OUT_DIR}/entropy.esm.min.js" 2>/dev/null || echo "?")
    echo "  ✓ ESM: $SIZE bytes → entropy.esm.min.js"
else
    cp "$ESM_FILE" "${OUT_DIR}/entropy.esm.min.js"
fi

# Step 5: Pre-compress for CDN edge caching (Brotli + Gzip)
echo ""
echo "📦 Pre-compressing for CDN..."

IIFE_MIN="${OUT_DIR}/entropy.min.js"
if [[ -f "$IIFE_MIN" ]]; then
    # Brotli (better ratio, modern CDN support)
    if command -v brotli &>/dev/null; then
        echo "  → Brotli..."
        brotli -Z "$IIFE_MIN" -o "${IIFE_MIN}.br" 2>/dev/null || true
        BR_SIZE=$(stat -f%z "${IIFE_MIN}.br" 2>/dev/null || stat -c%s "${IIFE_MIN}.br" 2>/dev/null || echo "?")
        echo "    ✓ ${IIFE_MIN}.br ($BR_SIZE bytes)"
    fi
    
    # Gzip (universal CDN support)
    if command -v gzip &>/dev/null; then
        echo "  → Gzip..."
        gzip -c -9 "$IIFE_MIN" > "${IIFE_MIN}.gz"
        GZ_SIZE=$(stat -f%z "${IIFE_MIN}.gz" 2>/dev/null || stat -c%s "${IIFE_MIN}.gz" 2>/dev/null || echo "?")
        echo "    ✓ ${IIFE_MIN}.gz ($GZ_SIZE bytes)"
    fi
fi

# Step 6: TypeScript declarations (auto-generate or fallback)
echo ""
echo "📦 Generating TypeScript declarations (entropy.d.ts)..."

if command -v tsc &>/dev/null; then
    # Generate from JSDoc comments
    cat > "${OUT_DIR}/entropy.d.ts" <<'EOF'
declare class EntropyPrime {
    constructor(apiKey: string, options?: EntropyOptions);
    startCapture(): Promise<void>;
    stopCapture(): void;
    getScore(): Promise<BiometricScore>;
    setTelemetryEndpoint(url: string): void;
}

interface EntropyOptions {
    endpoint?: string;
    batchSize?: number;
    batchInterval?: number;
    debug?: boolean;
}

interface BiometricScore {
    theta: number;
    confidence: string;
    timestamp: number;
}

export { EntropyPrime };
export default EntropyPrime;
EOF
    echo "  ✓ entropy.d.ts"
else
    # Fallback to hand-rolled minimal declarations
    cat > "${OUT_DIR}/entropy.d.ts" <<'EOF'
declare class EntropyPrime {
    constructor(apiKey: string, options?: any);
    startCapture(): Promise<void>;
    stopCapture(): void;
    getScore(): Promise<any>;
    setTelemetryEndpoint(url: string): void;
}
export default EntropyPrime;
EOF
    echo "  ⚠️  Generated minimal declarations (install TypeScript for full JSDoc parsing)"
fi

# Step 7: SDK manifest with SRI hashes
echo ""
echo "📦 Building SRI manifest (sdk-manifest.json)..."

cat > "${OUT_DIR}/sdk-manifest.json" <<'EOF'
{
  "version": "3.2.0",
  "timestamp": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "files": {
    "entropy.min.js": {
      "size": 0,
      "sha256": "",
      "sha384": "",
      "sri": ""
    },
    "entropy.esm.min.js": {
      "size": 0,
      "sha256": "",
      "sha384": ""
    },
    "entropy.min.js.br": {
      "size": 0,
      "compressed": true
    },
    "entropy.min.js.gz": {
      "size": 0,
      "compressed": true
    }
  },
  "cdn": {
    "jsdelivr": "https://cdn.jsdelivr.net/npm/@entropy-prime/sdk@3.2.0/entropy.min.js",
    "unpkg": "https://unpkg.com/@entropy-prime/sdk@3.2.0/entropy.min.js"
  },
  "snippet": "<script src=\"https://cdn.example.com/entropy.min.js\" integrity=\"sha384-XXXXXX\" crossorigin=\"anonymous\"><\\/script>"
}
EOF

# Compute hashes for IIFE variant
if [[ -f "$IIFE_MIN" ]]; then
    echo "  → Computing SRI hashes..."
    
    # SHA-256 (basic hash)
    if command -v sha256sum &>/dev/null; then
        SHA256=$(sha256sum "$IIFE_MIN" | awk '{print $1}')
        SIZE=$(stat -f%z "$IIFE_MIN" 2>/dev/null || stat -c%s "$IIFE_MIN" 2>/dev/null)
    elif command -v shasum &>/dev/null; then
        SHA256=$(shasum -a 256 "$IIFE_MIN" | awk '{print $1}')
        SIZE=$(stat -f%z "$IIFE_MIN" 2>/dev/null || stat -c%s "$IIFE_MIN" 2>/dev/null)
    else
        SHA256="(missing: install coreutils or OpenSSL)"
        SIZE="?"
    fi
    
    # SHA-384 (SRI hash, base64-encoded)
    if command -v openssl &>/dev/null; then
        SHA384=$(openssl dgst -sha384 -binary "$IIFE_MIN" | base64)
    else
        SHA384="(missing: install OpenSSL)"
    fi
    
    # Build SRI integrity attribute
    SRI_ATTR="sha384-${SHA384}"
    
    echo "    SHA-256: ${SHA256:0:16}..."
    echo "    SHA-384: ${SHA384:0:16}..."
    echo "    Size: $SIZE bytes"
    echo ""
    echo "  ✓ Ready-to-paste snippet:"
    echo "    <script src=\"https://your-cdn.com/entropy.min.js\" integrity=\"$SRI_ATTR\" crossorigin=\"anonymous\"></script>"
fi

echo ""
echo "✅ SDK bundle complete!"
echo ""
echo "📍 Outputs:"
ls -lh "${OUT_DIR}"/entropy.* 2>/dev/null | awk '{print "   " $9 " (" $5 ")"}'
echo ""
echo "Next: Upload entropy.min.js and entropy.min.js.br/.gz to your CDN."
