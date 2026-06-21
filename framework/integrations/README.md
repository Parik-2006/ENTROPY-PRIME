# framework/integrations — (Phase 5, deferred)

Framework adapters so third-party stacks can drop Entropy Prime in with
minimal glue. Empty at the facade stage.

## Planned adapters
- `flask/`    request middleware calling `/v1/verify`
- `express/`  Node middleware
- `fastapi/`  dependency wrapper
- `wordpress/` plugin stub

Each adapter is a thin client over the public REST API (`/v1/*`) + the JS SDK.
