/**
 * The voice detector measured on the corpus from `corpus.py` (and against the
 * silero one, on a checkout that has it), through the same path a call takes:
 * opus at discord's bitrate,
 * decoded, pushed a frame at a time into the real SpeechBuffer, with the sweep
 * running on the same twenty millisecond clock.
 *
 *     node tools/vad_bench/bench.js
 *     node tools/vad_bench/bench.js --hangovers 300,400,500 --json out.json
 *     node tools/vad_bench/bench.js --engines classic,silero
 *
 * "open" is a microphone that transmits all the time; "gated" is discord's own
 * voice activity closing the stream in the pauses, which is the default in a
 * real call and where the detector has the least to do.
 */

const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');

const ROOT = path.resolve(__dirname, '..', '..');
const BOT = path.join(ROOT, 'src/core/skills/voice/bot');
const botRequire = createRequire(path.join(BOT, 'package.json'));

const { OpusEncoder } = botRequire('@discordjs/opus');
const { createSpeechBuffer, PREROLL_MS } = require(path.join(BOT, 'classes/SpeechBuffer'));
const { createVoiceActivity } = require(path.join(BOT, 'classes/VoiceActivity'));

const FRAME_MS = 20;
const FRAME_BYTES = 3840;
// how long discord's own gate stays open after the voice stops. Not published;
// an assumption, and the same one for both detectors.
const GATE_RELEASE_MS = 300;
const BITRATE = 64000;

function args() {
    const out = {
        corpus: path.join(ROOT, 'data/vad_bench'),
        model: path.join(ROOT, 'data/models/silero/silero_vad_16k_op15.onnx'),
        hangovers: [500, 400, 300],
        engines: ['classic'],
        json: null,
        only: null,
    };
    const argv = process.argv.slice(2);
    for (let i = 0; i < argv.length; i += 2) {
        const [key, value] = [argv[i].replace(/^--/, ''), argv[i + 1]];
        if (key === 'hangovers') out.hangovers = value.split(',').map(Number);
        else if (key === 'engines') out.engines = value.split(',');
        else if (key === 'only') out.only = value.split(',');
        else if (key in out) out[key] = value;
        else throw new Error(`unknown option --${key}`);
    }
    return out;
}

/** What discord would deliver for one scenario: every frame through opus. */
function throughOpus(pcm) {
    const encoder = new OpusEncoder(48000, 2);
    encoder.setBitrate(BITRATE);
    const frames = [];
    for (let at = 0; at + FRAME_BYTES <= pcm.length; at += FRAME_BYTES) {
        frames.push(encoder.decode(encoder.encode(pcm.subarray(at, at + FRAME_BYTES))));
    }
    return frames;
}

/** Whether discord's gate would be sending the frame that ends at `t` ms. */
function gateOpen(turns, t) {
    const s = t / 1000;
    return turns.some((turn) => turn.regions.some(([a, b]) => a <= s && s - FRAME_MS / 1000 <= b + GATE_RELEASE_MS / 1000));
}

function run(frames, turns, { factory, hangoverMs, gated, beaSpeaking = false }) {
    const buffer = createSpeechBuffer({ hangoverMs, createActivity: factory });
    const emitted = [];
    let ducks = 0;
    let interrupts = 0;
    let onsetAt = null;
    let cpu = 0n;
    let pushed = 0;

    for (let i = 0; i < frames.length; i += 1) {
        const t = (i + 1) * FRAME_MS;
        let report = null;
        if (!gated || gateOpen(turns, t)) {
            const was = buffer.open;
            const t0 = process.hrtime.bigint();
            report = buffer.push(frames[i], { now: t, beaSpeaking });
            cpu += process.hrtime.bigint() - t0;
            pushed += 1;
            if (!was && buffer.open && onsetAt === null) onsetAt = t;
        } else {
            report = buffer.gap(t, { beaSpeaking });
        }
        if (report.duck) ducks += 1;
        if (report.interrupt) interrupts += 1;
        if (report.ended) {
            const turn = buffer.take();
            emitted.push({ onsetAt, emitAt: t, kept: Boolean(turn), ms: turn ? turn.ms : 0 });
            if (!buffer.open) onsetAt = null;
        }
    }
    return { emitted, ducks, interrupts, cpuMs: Number(cpu) / 1e6, audioMs: pushed * FRAME_MS };
}

const overlaps = (a0, a1, b0, b1) => a0 < b1 && b0 < a1;

function score(turns, { emitted }, hangoverMs) {
    const kept = emitted.filter((e) => e.kept);
    const result = {
        turns: turns.length, emitted: kept.length, dropped: emitted.length - kept.length,
        falseTurns: 0, merges: 0, splits: 0, missed: 0, clipped: 0,
        endLatency: [], onsetDelay: [], earlyCuts: 0,
    };

    // what each sent turn was: nothing, one real turn, or several run together
    for (const e of kept) {
        const from = (e.onsetAt - PREROLL_MS) / 1000;
        const to = e.emitAt / 1000;
        const hit = turns.filter((t) => overlaps(from, to, t.start, t.end));
        if (hit.length === 0) result.falseTurns += 1;
        if (hit.length > 1) result.merges += 1;
    }

    for (const turn of turns) {
        const pieces = kept.filter((e) => overlaps((e.onsetAt - PREROLL_MS) / 1000, e.emitAt / 1000, turn.start, turn.end));
        if (pieces.length === 0) {
            result.missed += 1;
            continue;
        }
        if (pieces.length > 1) result.splits += 1;
        // sent before the person had finished: she may answer half a sentence
        if (pieces[0].emitAt / 1000 < turn.end) result.earlyCuts += 1;
        const first = pieces[0];
        if ((first.onsetAt - PREROLL_MS) / 1000 > turn.start) result.clipped += 1;
        result.onsetDelay.push(first.onsetAt - turn.start * 1000);
        const last = pieces[pieces.length - 1];
        result.endLatency.push(last.emitAt - turn.end * 1000);
    }
    result.hangoverMs = hangoverMs;
    return result;
}

function pct(values, p) {
    if (!values.length) return NaN;
    const sorted = [...values].sort((a, b) => a - b);
    return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}

function main() {
    const opts = args();
    const scenarios = fs.readdirSync(opts.corpus)
        .filter((f) => f.endsWith('.json'))
        .map((f) => JSON.parse(fs.readFileSync(path.join(opts.corpus, f), 'utf8')))
        .filter((s) => !opts.only || opts.only.includes(s.name))
        .sort((a, b) => a.name.localeCompare(b.name));
    if (!scenarios.length) throw new Error(`no corpus in ${opts.corpus}: run tools/vad_bench/corpus.py`);

    const factories = { classic: (o) => createVoiceActivity(o) };
    // the neural detector is optional: only there on a checkout that has it
    if (opts.engines.includes('silero')) {
        const { createSileroActivity } = require(path.join(BOT, 'classes/SileroActivity'));
        const { loadWeights } = require(path.join(BOT, 'classes/Silero'));
        const weights = loadWeights(opts.model);
        factories.silero = (o) => createSileroActivity(weights, o);
    }

    const rows = [];
    for (const scenario of scenarios) {
        const frames = throughOpus(fs.readFileSync(path.join(opts.corpus, `${scenario.name}.pcm`)));
        const modes = scenario.turns.length && scenario.background === 'none' ? [false, true] : [false];
        for (const gated of modes) {
            for (const engine of opts.engines) {
                for (const hangoverMs of opts.hangovers) {
                    const outcome = run(frames, scenario.turns, { factory: factories[engine], hangoverMs, gated });
                    const s = score(scenario.turns, outcome, hangoverMs);
                    // the same noise while she is talking: what it would do to her
                    const over = scenario.noise_only
                        ? run(frames, [], { factory: factories[engine], hangoverMs, gated, beaSpeaking: true })
                        : { ducks: 0, interrupts: 0 };
                    rows.push({
                        ducks: over.ducks, interrupts: over.interrupts,
                        scenario: scenario.name, mode: gated ? 'gated' : 'open', engine, hangoverMs,
                        noiseOnly: Boolean(scenario.noise_only),
                        cpuMsPerS: outcome.audioMs ? (outcome.cpuMs / outcome.audioMs) * 1000 : 0,
                        ...s,
                    });
                }
            }
        }
    }

    print(rows, opts);
    if (opts.json) fs.writeFileSync(opts.json, JSON.stringify(rows, null, 1));
}

function print(rows, opts) {
    const pad = (v, n) => String(v).padStart(n);
    const fmt = (v) => (Number.isNaN(v) ? '-' : Math.round(v));
    console.log(`\n${'scenario'.padEnd(16)} ${'mode'.padEnd(5)} ${'engine'.padEnd(7)} hang | end p50  p95 | onset p50 | split merge miss early clip | false drop duck int | cpu ms/s`);
    for (const r of rows) {
        console.log(`${r.scenario.padEnd(16)} ${r.mode.padEnd(5)} ${r.engine.padEnd(7)} ${pad(r.hangoverMs, 4)} |`
            + ` ${pad(fmt(pct(r.endLatency, 50)), 7)} ${pad(fmt(pct(r.endLatency, 95)), 4)} |`
            + ` ${pad(fmt(pct(r.onsetDelay, 50)), 9)} |`
            + ` ${pad(r.splits, 5)} ${pad(r.merges, 5)} ${pad(r.missed, 4)} ${pad(r.earlyCuts, 5)} ${pad(r.clipped, 4)} |`
            + ` ${pad(r.falseTurns, 5)} ${pad(r.dropped, 4)} ${pad(r.ducks, 4)} ${pad(r.interrupts, 3)}`
            + ` | ${pad(r.cpuMsPerS.toFixed(1), 8)}`);
    }

    // one line per configuration: every speech scenario in open mode pooled,
    // and every noise-only scenario for what it sends that nobody said
    console.log('\nsummary (open mic, speech scenarios pooled; noise = noise-only scenarios)');
    console.log(`${'engine'.padEnd(7)} hang | end p50  p95 | onset p50 | splits merges missed early clipped | false(speech) false(noise) ducks ints | cpu ms/s`);
    for (const engine of opts.engines) {
        for (const hangoverMs of opts.hangovers) {
            const mine = rows.filter((r) => r.engine === engine && r.hangoverMs === hangoverMs && r.mode === 'open');
            const speech = mine.filter((r) => !r.noiseOnly);
            const noise = mine.filter((r) => r.noiseOnly);
            const sum = (list, k) => list.reduce((a, r) => a + r[k], 0);
            const ends = speech.flatMap((r) => r.endLatency);
            const onsets = speech.flatMap((r) => r.onsetDelay);
            const turns = sum(speech, 'turns');
            console.log(`${engine.padEnd(7)} ${pad(hangoverMs, 4)} |`
                + ` ${pad(fmt(pct(ends, 50)), 7)} ${pad(fmt(pct(ends, 95)), 4)} | ${pad(fmt(pct(onsets, 50)), 9)} |`
                + ` ${pad(`${sum(speech, 'splits')}/${turns}`, 6)} ${pad(sum(speech, 'merges'), 6)} ${pad(sum(speech, 'missed'), 6)}`
                + ` ${pad(sum(speech, 'earlyCuts'), 5)} ${pad(sum(speech, 'clipped'), 7)} |`
                + ` ${pad(sum(speech, 'falseTurns'), 13)} ${pad(sum(noise, 'falseTurns'), 12)}`
                + ` ${pad(sum(noise, 'ducks'), 5)} ${pad(sum(noise, 'interrupts'), 4)} |`
                + ` ${pad((sum(mine, 'cpuMsPerS') / mine.length).toFixed(1), 8)}`);
        }
    }
}

main();
