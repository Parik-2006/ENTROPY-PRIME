# Minimal Integration

The smallest realistic integration of Entropy Prime into a login flow.

- `app.py` — server-side, uses the **Python SDK** (`framework/sdk/python`).
- `index.html` — browser-side, uses the **JavaScript SDK** (`framework/sdk/js`).

Both require a running framework server (default `http://localhost:8000`) and
hit the versioned `/v1` API. The flow: authenticate → `score()` the behavioral
signals → if `shadow_mode` deny, else `trust()`-gate the action.
