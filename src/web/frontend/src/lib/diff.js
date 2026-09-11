/**
 * A line diff, so a prompt conflict can be read instead of squinted at.
 *
 * Longest common subsequence, which is what every diff tool uses and what makes
 * "these forty lines are the same, these three are not" fall out of the data
 * rather than out of guesswork. Prompts are hundreds of lines, so the quadratic
 * table is nothing; the cap below is only there so a pathological paste cannot
 * lock the tab up.
 */

const MAX_LINES = 4000;

/**
 * Pairs the two versions line by line.
 * Each row is { left, right, leftNumber, rightNumber, state } where state is
 * 'same' | 'changed' | 'added' | 'removed'.
 */
export function alignLines(mine = '', theirs = '') {
    const a = mine.split('\n');
    const b = theirs.split('\n');

    if (a.length > MAX_LINES || b.length > MAX_LINES) {
        return { rows: pairBluntly(a, b), truncated: true };
    }

    const table = lcsTable(a, b);
    const rows = [];
    let i = 0;
    let j = 0;

    while (i < a.length && j < b.length) {
        if (a[i] === b[j]) {
            rows.push({ left: a[i], right: b[j], leftNumber: i + 1, rightNumber: j + 1, state: 'same' });
            i += 1;
            j += 1;
        } else if (table[i + 1][j] >= table[i][j + 1]) {
            rows.push({ left: a[i], right: null, leftNumber: i + 1, rightNumber: null, state: 'removed' });
            i += 1;
        } else {
            rows.push({ left: null, right: b[j], leftNumber: null, rightNumber: j + 1, state: 'added' });
            j += 1;
        }
    }
    while (i < a.length) {
        rows.push({ left: a[i], right: null, leftNumber: i + 1, rightNumber: null, state: 'removed' });
        i += 1;
    }
    while (j < b.length) {
        rows.push({ left: null, right: b[j], leftNumber: null, rightNumber: j + 1, state: 'added' });
        j += 1;
    }

    return { rows: pairAdjacent(rows), truncated: false };
}

/** How many lines differ at all — the number worth putting on a summary line. */
export function countChanges(rows) {
    return rows.filter((row) => row.state !== 'same').length;
}

/**
 * Collapses a removal immediately followed by an addition into one row.
 * An edited line is one thing that happened, and reading it as a deletion above
 * an insertion makes every rewording look twice as large as it is.
 */
function pairAdjacent(rows) {
    const paired = [];
    for (let index = 0; index < rows.length; index += 1) {
        const row = rows[index];
        const next = rows[index + 1];
        if (row.state === 'removed' && next?.state === 'added') {
            paired.push({
                left: row.left,
                right: next.right,
                leftNumber: row.leftNumber,
                rightNumber: next.rightNumber,
                state: 'changed',
            });
            index += 1;
        } else {
            paired.push(row);
        }
    }
    return paired;
}

function pairBluntly(a, b) {
    const rows = [];
    for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
        const left = index < a.length ? a[index] : null;
        const right = index < b.length ? b[index] : null;
        rows.push({
            left,
            right,
            leftNumber: left === null ? null : index + 1,
            rightNumber: right === null ? null : index + 1,
            state: left === right ? 'same' : 'changed',
        });
    }
    return rows;
}

function lcsTable(a, b) {
    const table = Array.from({ length: a.length + 1 }, () => new Uint32Array(b.length + 1));
    for (let i = a.length - 1; i >= 0; i -= 1) {
        for (let j = b.length - 1; j >= 0; j -= 1) {
            table[i][j] = a[i] === b[j]
                ? table[i + 1][j + 1] + 1
                : Math.max(table[i + 1][j], table[i][j + 1]);
        }
    }
    return table;
}
