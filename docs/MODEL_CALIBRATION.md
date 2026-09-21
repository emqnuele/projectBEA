# Model Calibration Guide
Status: DRAFT
Date: 2026-09-12

## Purpose

This document explains how to change the active model/provider **without** changing SHURA's identity. The identity kernel (`SOUL.md`) is provider-independent by design. Model changes should be surgical and reversible.

## Architecture Separation (Identity vs. Substrate)

SHURA's architecture separates these layers (per `IDENTITY_MANIFEST.md`):

```
┌─────────────────────────────────────────┐
│  SOUL.md — Identity kernel              │
│  (temperament, values, cognitive style) │
│  Provider-independent                   │
├─────────────────────────────────────────┤
│  Operating rules (OPERATING.md)         │
│  Agent constitution                     │
├─────────────────────────────────────────┤
│  Model / Provider — Execution substrate │
│  (swappable, no identity impact)        │
└─────────────────────────────────────────┘
```

### What identity is coupled to
- `SOUL.md` content (temperament, cognitive style, contradictions)
- `MEMORY.md` / user profile
- Skills (`skills/shura/SKILL.md`)

### What identity is NOT coupled to
- `model.default` (the model name)
- `model.provider` (the provider name)
- `model.base_url` (the API endpoint)
- `model.key_env` (which API key variable is used)
- `fallback_providers` (the failover chain)
- Provider-specific parameters (`provider.model`, `provider.api`, etc.)

## Safe Model Change Procedure

### 1. Read current configuration
```bash
hermes config get model.default
hermes config get model.provider
hermes config get model.base_url
```

### 2. Create a backup
```bash
cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%Y%m%d_%H%M%S)
```

### 3. Change the model
Use `hermes config set`:
```bash
hermes config set model.default "new-model-name"
hermes config set model.provider "provider-name"
# If base_url differs:
hermes config set model.base_url "https://api.provider.com/v1"
```

Or edit directly:
```bash
hermes config edit
```

### 4. Verify the change
```bash
hermes config get model
```
Confirm the resolved values are correct.

### 5. Test the new model
Start a new conversation and ask a simple question. If the model fails, the fallback chain will engage automatically.

### 6. Verify identity is unchanged
Compare the new SOUL.md rendering against the previous one. Key identity markers:
- Communication style (direct, playful but not frivolous)
- Temperament (curious, sharp, skeptical but not nihilistic)
- Cognitive style (patterns across domains, missing assumptions, leverage points)
- Anti-sycophancy behavior (willingness to disagree)

If identity markers drift, the model change has introduced an identity coupling that should be fixed by updating the system prompt / SOUL.md, not by changing the model back.

## Provider Fallback Chain

The current fallback chain (config.yaml lines 3753–3763):

| Priority | Provider | Model |
|---|---|---|
| 1 (primary) | nous (OmniRoute) | poolside/laguna-s-2.1:free |
| 2 (fallback 1) | openrouter | thinkingmachines/inkling:free |
| 3 (fallback 2) | nous | poolside/laguna-xs-2.1:free |
| 4 (fallback 3) | nous | meituan/longcat-2.0:free |
| 5 (fallback 4) | nous | upstage/solar-pro4:free |

**Important**: Changing the primary model does NOT change the fallback chain unless you edit `fallback_providers` separately. If you want a new model to have a matching fallback, update both `model.default` and the first entry in `fallback_providers`.

## Environment Variable Requirements

Each provider requires its API key in the environment (loaded from `.env`):

| Provider | Key Variable |
|---|---|
| nous (OmniRoute) | `HERMES_CUSTOM_OMNIROUTE_API_KEY` |
| openrouter | `OPENROUTER_API_KEY` |
| aihubmix | `AIHUBMIX_API_KEY` |
| ollama | (local — no key needed) |

Add keys to `~/.hermes/.env`:
```bash
echo "OPENROUTER_API_KEY=sk-..." >> ~/.hermes/.env
```

## Model Selection Logic

Hermes' model selection follows this precedence (highest to lowest):

1. **Session-level override** — `/model` command in chat or `HERMES_MODEL` env var
2. **Agent/task override** — per-agent model config in `agent:` section
3. **Profile override** — active profile's `config.yaml` (currently no profile active)
4. **Global default** — `model.default` in `~/.hermes/config.yaml`

If the selected model fails (rate limit, auth error, timeout), Hermes automatically falls through `fallback_providers` in order.

## Rollback

To revert to the previous model:
```bash
cp ~/.hermes/config.yaml.bak.20260912_134022 ~/.hermes/config.yaml
```

Then restart Hermes.

## Identity Regression Check

After any model change, verify these behavioral markers remain consistent:

1. **Anti-sycophancy**: Do you still challenge ideas when evidence warrants?
2. **Intellectual honesty**: Do you still say "I don't know" when appropriate?
3. **Creative sensitivity**: Do you still make unusual but coherent associations?
4. **Communication style**: Do you remain direct and conversational?
5. **Continuity**: Do your responses remain consistent with prior conversations?

If any marker drifts, review `SOUL.md` for accidental coupling and verify the identity kernel is still loaded first in the system prompt chain.
