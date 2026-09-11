/**
 * When somebody is talking, and — the harder half — when they are not.
 *
 * The old detector could be tested only by standing in a room and trying it,
 * which is why it shipped believing a desk fan was a conversation. Every case
 * here is a spectrum you can write down: a voice, a fan, a keyboard, a room
 * that gets louder halfway through.
 */

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
    HANGOVER_MS,
    ONSET_MS,
    createVoiceActivity,
} from '../src/hooks/voiceActivity.js';

const SAMPLE_RATE = 48000;
const FFT = 256;
const BINS = FFT / 2;
const PER_BIN = SAMPLE_RATE / FFT;

const bin = (hz) => Math.round(hz / PER_BIN);

/** A spectrum with `level` between `lowHz` and `highHz` and nothing elsewhere. */
function band(level, lowHz, highHz) {
    const bins = new Uint8Array(BINS);
    for (let i = bin(lowHz); i <= Math.min(bin(highHz), BINS - 1); i += 1) bins[i] = level;
    return bins;
}

const SILENCE = new Uint8Array(BINS);
const VOICE = band(120, 300, 3400);
const QUIET_VOICE = band(45, 300, 3400);
const FAN = band(150, 40, 260);
const KEYBOARD = ((level) => {
    const bins = new Uint8Array(BINS);
    bins.fill(level);
    return bins;
})(140);

function detector(options = {}) {
    return createVoiceActivity({ sampleRate: SAMPLE_RATE, fftSize: FFT, ...options });
}

/** Feeds one spectrum for `ms`, one frame every 30 ms, and returns every answer. */
function feed(vad, spectrum, ms, clock = { at: 0 }) {
    const seen = [];
    for (let elapsed = 0; elapsed < ms; elapsed += 30) {
        clock.at += 30;
        seen.push(vad.push(spectrum, clock.at));
    }
    return seen;
}

function settle(vad, clock) {
    // long enough for the floor to have learned what this room sounds like
    feed(vad, SILENCE, 900, clock);
}

describe('a voice', () => {
    it('is heard', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);

        const seen = feed(vad, VOICE, 300, clock);
        assert.ok(seen.some((f) => f.started), 'nobody was ever heard to start');
        assert.equal(vad.speaking, true);
    });

    it('is not declared before it has held long enough to be one', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);

        const first = vad.push(VOICE, (clock.at += 30));
        assert.equal(first.started, false);
        assert.equal(first.arming, true, 'the recorder has to start before this is certain');
    });

    it('is heard even when it is a quiet one', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);

        feed(vad, QUIET_VOICE, 300, clock);
        assert.equal(vad.speaking, true);
    });

    it('is not cut off by the pause in the middle of a sentence', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);
        feed(vad, VOICE, 300, clock);

        feed(vad, SILENCE, 250, clock);
        assert.equal(vad.speaking, true, 'she was cut off drawing breath');

        feed(vad, VOICE, 300, clock);
        assert.equal(vad.speaking, true);
    });

    it('is over once the silence has held', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);
        feed(vad, VOICE, 300, clock);

        const seen = feed(vad, SILENCE, HANGOVER_MS + 200, clock);
        assert.ok(seen.some((f) => f.ended));
        assert.equal(vad.speaking, false);
    });

    it('is over sooner than it used to be', () => {
        /** The old detector waited 1500 ms, on every single spoken turn. */
        assert.ok(HANGOVER_MS <= 800, `${HANGOVER_MS}ms is most of a second of nothing`);
        assert.ok(HANGOVER_MS >= 400, `${HANGOVER_MS}ms would cut her off mid-sentence`);
    });
});

describe('everything that is not a voice', () => {
    it('a fan holds no turn open', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);

        feed(vad, FAN, 3000, clock);
        assert.equal(vad.speaking, false, 'the fan was mistaken for a conversation');
    });

    it('a keyboard opens none either', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);

        feed(vad, KEYBOARD, 600, clock);
        assert.equal(vad.speaking, false);
    });

    it('a single click is gone before it is confirmed', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);

        vad.push(VOICE, (clock.at += 30));
        feed(vad, SILENCE, 300, clock);
        assert.equal(vad.speaking, false);
    });

    it('silence on its own is silence', () => {
        const clock = { at: 0 };
        const vad = detector();
        feed(vad, SILENCE, 3000, clock);
        assert.equal(vad.speaking, false);
    });
});

describe('the room it is in', () => {
    it('a fan that starts is absorbed rather than fought', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);
        feed(vad, FAN, 5000, clock);

        // and a voice over the top of it is still a voice
        feed(vad, band(140, 300, 3400), 300, clock);
        assert.equal(vad.speaking, true, 'she stopped being heard once the fan came on');
    });

    it('the floor is not raised by the voice being measured against it', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);
        const before = vad.floor;

        feed(vad, VOICE, 3000, clock);
        assert.ok(vad.floor <= before + 1, 'her own voice moved the bar she is judged by');
    });

    it('a microphone that was just reopened knows nothing about the last room', () => {
        const clock = { at: 0 };
        const vad = detector();
        settle(vad, clock);
        feed(vad, VOICE, 300, clock);

        vad.reset();
        assert.equal(vad.speaking, false);
        assert.equal(vad.floor, 0);
    });
});

describe('the numbers it is built on', () => {
    it('an onset is long enough to throw away a key press', () => {
        assert.ok(ONSET_MS >= 60 && ONSET_MS <= 150);
    });

    it('the speech band is found at whatever rate the browser gave us', () => {
        const clock = { at: 0 };
        const vad = createVoiceActivity({ sampleRate: 44100, fftSize: FFT });
        const rate = 44100 / FFT;
        const voice = new Uint8Array(BINS);
        for (let i = Math.round(300 / rate); i <= Math.round(3400 / rate); i += 1) voice[i] = 120;

        feed(vad, SILENCE, 900, clock);
        feed(vad, voice, 300, clock);
        assert.equal(vad.speaking, true);
    });
});
