# framework/sdk — Integration SDKs  [IMPLEMENTED]

Client SDKs that let applications consume Entropy Prime as a framework.

```
sdk/
├── js/        JavaScript SDK (browser, fetch-based, zero deps)
│              entropy-prime.js  ·  package.json  ·  README.md
└── python/    Python SDK (stdlib only, zero deps)
               entropy_prime/{__init__,client}.py  ·  pyproject.toml  ·  README.md
```

Both target the versioned `/v1` API mounted by `framework.api_gateway` and
expose the same surface: enroll/login, `score()`, `verify()` (continuous-auth
heartbeat), and `trust()` (transaction gate).

- **JS**: `new EntropyPrime({apiUrl}).attach(form)` → `flush()` posts `/v1/score`.
  Production deployments plug in the full TensorFlow.js engine from
  `src/services/biometrics.js` via `setEngine()`.
- **Python**: `EntropyPrime(api_url=...)` for server-to-server integration.

See each subfolder's README for usage. A minimal end-to-end integration using
both SDKs is in `examples/integration_minimal/`.
