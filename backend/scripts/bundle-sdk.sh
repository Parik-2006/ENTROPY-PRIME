#!/usr/bin/env bash
# =============================================================
#  scripts/bundle-sdk.sh
#  Builds entropy.min.js — a self-contained CDN-ready bundle
#  of the Entropy Prime client-side biometrics SDK.
#
#  Output:
#    dist/entropy.min.js        (minified IIFE, ~30-80 KB gzip)
#    dist/entropy.min.js.map    (source map for debugging)
#    dist/entropy.min.js.br     (Brotli pre-compressed for CDN)
#    dist/entropy.min.js.gz     (Gzip  pre-compressed for CDN)
#    dist/entropy.esm.min.js    (ES-module variant for bundlers)
#    dist/entropy.d.ts          (TypeScript declarations)
#    dist/sdk-manifest.json     (integrity hashes + build meta)
# =============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
SDK_ENTRY="${ROOT_DIR}/src/sdk/index.ts"
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
VERSION=$(node -p "require('${ROOT_DIR}/package.json').version" 2>/dev/null || echo "1.0.0")

# ── Colour helpers ────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[SDK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[SDK]${NC} $*"; }
error() { echo -e "${RED}[SDK]${NC} $*" >&2; exit 1; }

info "Entropy Prime SDK Bundler v${VERSION}"
info "Build date: ${BUILD_DATE}"
echo ""

# ── Dependency checks ─────────────────────────────────────────
command -v node  >/dev/null 2>&1 || error "node is required."
command -v npm   >/dev/null 2>&1 || error "npm is required."

# Check for brotli / gzip (optional, warn if absent)
HAS_BROTLI=false; HAS_GZIP=false
command -v brotli >/dev/null 2>&1 && HAS_BROTLI=true || warn "brotli not found; skipping .br output."
command -v gzip   >/dev/null 2>&1 && HAS_GZIP=true   || warn "gzip not found; skipping .gz output."

# ── Prepare output directory ──────────────────────────────────
info "Preparing dist/ directory..."
mkdir -p "${DIST_DIR}"
rm -f "${DIST_DIR}"/entropy.*  "${DIST_DIR}"/sdk-manifest.json

# ── Ensure vite and rollup plugins are available ──────────────
info "Checking build toolchain..."
cd "${ROOT_DIR}"
if [ ! -d "node_modules" ]; then
    info "Installing dependencies..."
    npm ci --ignore-scripts
fi

# ── Generate TypeScript declarations ─────────────────────────
info "Generating TypeScript declarations..."
# Emit only the SDK entry declarations; suppress errors from app code
npx tsc \
    --declaration \
    --emitDeclarationOnly \
    --isolatedModules \
    --esModuleInterop \
    --moduleResolution node \
    --outDir "${DIST_DIR}" \
    --rootDir "${ROOT_DIR}/src/sdk" \
    "${ROOT_DIR}/src/sdk/"*.ts 2>/dev/null || \
# Fallback: generate a minimal hand-rolled .d.ts if tsc fails
cat > "${DIST_DIR}/entropy.d.ts" << 'EOF'
/**
 * Entropy Prime SDK — Type Declarations
 * @version 1.0.0
 */

export interface EntropyConfig {
  /** Backend API base URL. Defaults to http://localhost:8000 */
  apiUrl?: string;
  /** Sensitivity threshold for bot detection (0–1). Default: 0.5 */
  threshold?: number;
  /** Enable verbose console logging. Default: false */
  debug?: boolean;
  /** Milliseconds between session heartbeats. Default: 30000 */
  heartbeatInterval?: number;
  /** Called when the humanity score is computed */
  onScore?: (score: number, label: "human" | "bot" | "uncertain") => void;
  /** Called when a session token is issued */
  onSession?: (token: string) => void;
  /** Called on any error */
  onError?: (err: Error) => void;
}

export interface BiometricSample {
  dwellTimes: number[];
  flightTimes: number[];
  velocities: number[];
  jitter: number[];
  pressures: number[];
}

export interface ScoreResult {
  theta: number;
  label: "human" | "bot" | "uncertain";
  hExp: number;
  sessionToken: string | null;
}

export declare class EntropyPrime {
  constructor(config?: EntropyConfig);
  /** Attach listeners to a form or the document */
  attach(target?: HTMLElement | Document): this;
  /** Detach all listeners and stop heartbeat */
  detach(): void;
  /** Force an immediate score flush to the backend */
  flush(): Promise<ScoreResult>;
  /** Current rolling humanity score (0–1) */
  readonly theta: number;
  /** Current session token (null before first score) */
  readonly sessionToken: string | null;
}

/** Convenience factory */
export declare function createEntropyPrime(config?: EntropyConfig): EntropyPrime;

/** UMD global exposed when loaded via <script> tag */
declare global {
  interface Window {
    EntropyPrime: typeof EntropyPrime;
    createEntropyPrime: typeof createEntropyPrime;
  }
}
EOF

info "TypeScript declarations written."

# ── IIFE bundle (CDN / <script> tag) ─────────────────────────
info "Building IIFE bundle (entropy.min.js)..."

cat > "${ROOT_DIR}/vite.sdk.config.mjs" << 'VITECONF'
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: {
      entry: "./src/sdk/index.ts",
      name: "EntropyPrime",
      fileName: () => "entropy.min.js",
      formats: ["iife"],
    },
    outDir: "dist",
    emptyOutDir: false,
    sourcemap: true,
    minify: "terser",
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
        pure_funcs: ["console.log", "console.info", "console.debug"],
        passes: 3,
      },
      mangle: { toplevel: true },
      format: { comments: false },
    },
    rollupOptions: {
      external: [],          // zero external deps — fully self-contained
      output: {
        banner: `/*! Entropy Prime SDK v${process.env.SDK_VERSION || "1.0.0"} | MIT | ${new Date().toISOString()} */`,
      },
    },
  },
});
VITECONF

SDK_VERSION="${VERSION}" npx vite build --config vite.sdk.config.mjs
rm -f "${ROOT_DIR}/vite.sdk.config.mjs"
info "IIFE bundle written: dist/entropy.min.js"

# ── ESM bundle (for bundlers / import maps) ───────────────────
info "Building ESM bundle (entropy.esm.min.js)..."

cat > "${ROOT_DIR}/vite.sdk.esm.config.mjs" << 'VITEESM'
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: {
      entry: "./src/sdk/index.ts",
      name: "EntropyPrime",
      fileName: () => "entropy.esm.min.js",
      formats: ["es"],
    },
    outDir: "dist",
    emptyOutDir: false,
    sourcemap: false,
    minify: "terser",
    terserOptions: {
      compress: { drop_console: true, passes: 2 },
      mangle: { module: true },
      format: { comments: false },
    },
    rollupOptions: { external: [] },
  },
});
VITEESM

npx vite build --config vite.sdk.esm.config.mjs
rm -f "${ROOT_DIR}/vite.sdk.esm.config.mjs"
info "ESM bundle written: dist/entropy.esm.min.js"

# ── Pre-compress for CDN ──────────────────────────────────────
if [ "$HAS_BROTLI" = true ]; then
    info "Pre-compressing with Brotli..."
    brotli -f -q 11 -o "${DIST_DIR}/entropy.min.js.br" "${DIST_DIR}/entropy.min.js"
    BROTLI_SIZE=$(wc -c < "${DIST_DIR}/entropy.min.js.br")
    info "Brotli size: ${BROTLI_SIZE} bytes"
fi

if [ "$HAS_GZIP" = true ]; then
    info "Pre-compressing with Gzip..."
    gzip -9 -k -f "${DIST_DIR}/entropy.min.js"
    GZIP_SIZE=$(wc -c < "${DIST_DIR}/entropy.min.js.gz")
    info "Gzip size: ${GZIP_SIZE} bytes"
fi

# ── Compute integrity hashes ──────────────────────────────────
info "Computing SRI hashes..."
IIFE_SIZE=$(wc -c < "${DIST_DIR}/entropy.min.js")
ESM_SIZE=$(wc -c  < "${DIST_DIR}/entropy.esm.min.js")

IIFE_SHA256=$(openssl dgst -sha256 -binary "${DIST_DIR}/entropy.min.js"     | openssl base64 -A)
ESM_SHA256=$(openssl dgst  -sha256 -binary "${DIST_DIR}/entropy.esm.min.js" | openssl base64 -A)
IIFE_SHA384=$(openssl dgst -sha384 -binary "${DIST_DIR}/entropy.min.js"     | openssl base64 -A)

# ── Write manifest ────────────────────────────────────────────
info "Writing sdk-manifest.json..."
cat > "${DIST_DIR}/sdk-manifest.json" << JSON
{
  "name": "entropy-prime-sdk",
  "version": "${VERSION}",
  "buildDate": "${BUILD_DATE}",
  "files": {
    "iife": {
      "path": "entropy.min.js",
      "bytes": ${IIFE_SIZE},
      "integrity": {
        "sha256": "sha256-${IIFE_SHA256}",
        "sha384": "sha384-${IIFE_SHA384}"
      }
    },
    "esm": {
      "path": "entropy.esm.min.js",
      "bytes": ${ESM_SIZE},
      "integrity": {
        "sha256": "sha256-${ESM_SHA256}"
      }
    }
  },
  "usage": {
    "cdn_script_tag": "<script src='https://cdn.example.com/entropy-prime@${VERSION}/entropy.min.js' integrity='sha384-${IIFE_SHA384}' crossorigin='anonymous'></script>",
    "esm_import": "import { EntropyPrime } from 'https://cdn.example.com/entropy-prime@${VERSION}/entropy.esm.min.js';"
  }
}
JSON

# ── Summary ───────────────────────────────────────────────────
echo ""
info "╔══════════════════════════════════════════════════╗"
info "║         SDK Bundle Complete ✓                    ║"
info "╠══════════════════════════════════════════════════╣"
info "║  IIFE  dist/entropy.min.js       ${IIFE_SIZE} bytes"
info "║  ESM   dist/entropy.esm.min.js   ${ESM_SIZE} bytes"
[ "$HAS_BROTLI" = true ] && info "║  .br   dist/entropy.min.js.br    ${BROTLI_SIZE} bytes"
[ "$HAS_GZIP"   = true ] && info "║  .gz   dist/entropy.min.js.gz    ${GZIP_SIZE} bytes"
info "║  Decl  dist/entropy.d.ts"
info "║  Meta  dist/sdk-manifest.json"
info "╚══════════════════════════════════════════════════╝"
echo ""
info "SRI hash (sha384, use in <script integrity='...'>):"
info "  sha384-${IIFE_SHA384}"
echo ""