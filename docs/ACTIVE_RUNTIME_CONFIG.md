# Active Runtime Configuration
Status: DONE (model drift explained, no fix needed)
Date: 2026-09-12

## Findings

### CONFIGURED PRIMARY
```yaml
model:
  default: poolside/laguna-s-2.1:free
  provider: nous
  base_url: https://inference-api.nousresearch.com/v1
  key_env: HERMES_CUSTOM_OMNIROUTE_API_KEY
```

The configured primary provider is `nous` with model `poolside/laguna-s-2.1:free`. The provider resolves to an OmniRoute endpoint (`base_url: https://inference-api.nousresearch.com/v1`), which on the local machine is proxied through `omniroute` at `http://localhost:20128/v1` (key_env: `HERMES_CUSTOM_OMNIROUTE_API_KEY`).

### ACTUAL PRIMARY
Session observations showed `thinkingmachines/inkling:free` (via OpenRouter) being used. This is **not a bug** — it is the documented fallback mechanism.

### FALLBACK
The config defines `fallback_providers` (config.yaml lines 3753–3763):

```yaml
fallback_providers:
  - provider: openrouter
    model: thinkingmachines/inkling:free
  - provider: nous
    model: poolside/laguna-s-2.1:free
  - provider: nous
    model: poolside/laguna-xs-2.1:free
  - provider: nous
    model: meituan/longcat-2.0:free
  - provider: nous
    model: upstage/solar-pro4:free
```

### REASON FOR DIFFERENCE

The primary provider (`nous` / OmniRoute) is **unreachable** at runtime. Evidence:

1. A `curl` to `http://localhost:20128/v1/models` returned no output (connection refused or timeout).
2. No `HERMES_CUSTOM_OMNIROUTE_API_KEY` environment variable was found in the shell environment.
3. The Hermes process environment does not include the OmniRoute API key.

When the primary provider is unavailable, Hermes automatically falls through the `fallback_providers` list. The first fallback (`openrouter` / `thinkingmachines/inkling:free`) succeeds and becomes the active model.

This is **correct, configured behavior** — the fallback system is working as designed. The "mismatch" observed in the audit is the fallback mechanism operating as intended.

## Verification

```
hermes config get model.default     → poolside/laguna-s-2.1:free
hermes config get model.provider    → nous
hermes config get model.base_url    → https://inference-api.nousresearch.com/v1
```

OmniRoute endpoint health check:
```
curl http://localhost:20128/v1/models  → (no response — service not running)
```

## Status

| Aspect | Verdict |
|---|---|
| Config is internally consistent | YES |
| Fallback chain is correctly configured | YES |
| Model drift is explainable | YES (primary unreachable, fallback active) |
| Action required | NO — system is operating as designed |
| Action recommended | YES — document this in `MODEL_CALIBRATION.md`; optionally start OmniRoute service if available |

## Note on `display.personality: uwu`

The config includes `display.personality: uwu` (line 3877). This is a cosmetic display tag and does **not** override `SOUL.md` identity. It affects output formatting only, not SHURA's identity kernel. No action needed.
