/**
 * The shape of the context window, as the engine derives it.
 *
 * The ratios themselves are never written here — they arrive with the schema,
 * from `src/core/mind/token_budget.py`, so there is one definition of what a
 * ceiling implies. This only mirrors the engine's rounding, so the number
 * under a slider being dragged matches the number that comes back after it is
 * saved.
 */

/** One share of the ceiling, rounded to a round number of tokens. */
export function derivedTokens(ceiling, ratio) {
    return Math.max(1000, Math.round((Number(ceiling) * ratio) / 1000) * 1000);
}

/**
 * What each derived number is currently worth, and where it comes from.
 *
 * A setting pinned to anything above zero wins over the ceiling — that is the
 * whole point of pinning it — and says so, so a slider that looks like it
 * moves everything cannot quietly be moving only part of it.
 */
export function windowShape(ceiling, derives = [], values = {}) {
    return derives.map(({ key, label, ratio }) => {
        const pinned = Number(values?.[key]) || 0;
        return {
            key,
            label,
            tokens: pinned > 0 ? pinned : derivedTokens(ceiling, ratio),
            pinned: pinned > 0,
        };
    });
}
