/**
 * Loads where only the one asked for last may land. Pure, so node can test it.
 */

/**
 * Wraps `load` so a result that finishes after a newer request was made is
 * handed to `discard` and resolves to null instead of being used.
 */
export function latestOnly(load, discard) {
    let asked = 0;
    return async (...args) => {
        const mine = ++asked;
        const result = await load(...args);
        if (mine !== asked) {
            discard(result);
            return null;
        }
        return result;
    };
}
