/**
 * When somebody in the call is talking, and — the harder half — when they have
 * finished.
 *
 * The gate this replaced could only be tested by sitting in a call and trying
 * it, which is why it shipped believing a desk fan was a conversation and that
 * a breath was the end of a sentence. Every case here is a buffer you can write
 * down: a voice, a fan, hiss, a pause inside a sentence, three people at once.
 */

const test = require('node:test');
const assert = require('node:assert');

const { createVoiceActivity, HANGOVER_MS, ONSET_MS } = require('../classes/VoiceActivity');
const { createSpeechBuffer } = require('../classes/SpeechBuffer');
const { downsampleMono16k, pcmToWav, BYTES_PER_MS } = require('../classes/Pcm');

const RATE = 48000;

/** `ms` of 48khz stereo built from a function of time in seconds. */
function pcm(ms, wave) {
    const buffer = Buffer.alloc(Math.round(ms * BYTES_PER_MS));
    for (let i = 0; i < buffer.length; i += 4) {
        const sample = Math.max(-32768, Math.min(32767, Math.round(wave((i / 4) / RATE))));
        buffer.writeInt16LE(sample, i);
        buffer.writeInt16LE(sample, i + 2);
    }
    return buffer;
}

// a harmonic stack in the speech range: crude, and deliberately the worst case
// of one — a real voice has formants that put even more of it inside the band
const speech = (f0 = 140, amp = 6000) => (t) => {
    let value = 0;
    for (let h = 1; h <= 18; h += 1) value += (1 / h) * Math.sin(2 * Math.PI * f0 * h * t);
    return (amp * value) / 2;
};

const fan = (amp = 6000) => (t) => amp * (0.8 * Math.sin(2 * Math.PI * 70 * t)
    + 0.4 * Math.sin(2 * Math.PI * 140 * t) + 0.1 * (Math.random() * 2 - 1));

const hiss = (amp = 6000) => (t) => amp * Math.sin(2 * Math.PI * 9000 * t);
const keyboard = (amp = 9000) => () => amp * (Math.random() * 2 - 1);
const silence = () => () => 0;

const VOICE = pcm(300, speech());
const QUIET_VOICE = pcm(300, speech(180, 900));
const DEEP_VOICE = pcm(300, speech(85));
const FAN = pcm(300, fan());
const HISS = pcm(300, hiss());
const ROOM = pcm(500, silence());

/** Feeds a buffer in the twenty-millisecond pieces the decoder delivers. */
function feed(vad, buffer) {
    const seen = [];
    const step = Math.round(20 * BYTES_PER_MS);
    for (let at = 0; at + step <= buffer.length; at += step) {
        seen.push(vad.push(buffer.subarray(at, at + step)));
    }
    return seen;
}

// --- who is talking ------------------------------------------------------

test('a voice is heard', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    const seen = feed(vad, VOICE);
    assert.ok(seen.some((f) => f.started), 'nobody was ever heard to start');
    assert.equal(vad.speaking, true);
});

test('a quiet voice is heard too', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, QUIET_VOICE);
    assert.equal(vad.speaking, true, 'a quiet speaker is still a speaker');
});

test('a deep voice is heard, which is the case the band nearly loses', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, DEEP_VOICE);
    assert.equal(vad.speaking, true);
});

test('a fan is not a conversation, however loud it is', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, pcm(2000, fan(12000)));
    assert.equal(vad.speaking, false);
});

test('hiss is not a conversation either', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, HISS);
    assert.equal(vad.speaking, false);
});

test('a hand on a keyboard is not somebody talking', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, pcm(400, keyboard()));
    assert.equal(vad.speaking, false);
});

test('a voice is not declared before it has held long enough to be one', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    const first = vad.push(VOICE.subarray(0, Math.round(20 * BYTES_PER_MS)));
    assert.equal(first.started, false, `${ONSET_MS}ms has to pass first`);
    assert.equal(first.arming, true, 'but it is already suspected');
});

test('a voice over a running pc is still a voice', () => {
    const vad = createVoiceActivity();
    const noisy = fan(4000);
    const voiced = speech(140, 6000);
    feed(vad, pcm(600, noisy));
    assert.equal(vad.speaking, false, 'the room alone is not speech');
    feed(vad, pcm(400, (t) => noisy(t) + voiced(t)));
    assert.equal(vad.speaking, true);
});

// --- when they have finished ---------------------------------------------

test('a pause inside a sentence does not end it', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, VOICE);

    const held = vad.silence(HANGOVER_MS - 100);
    assert.equal(held.ended, false, 'a breath is not the end of a sentence');
    assert.equal(vad.speaking, true);
});

test('a silence long enough does end it', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, VOICE);

    assert.equal(vad.silence(HANGOVER_MS + 20).ended, true);
    assert.equal(vad.speaking, false);
});

test('a turn ends once, not on every tick after it', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, VOICE);

    assert.equal(vad.silence(HANGOVER_MS + 20).ended, true);
    assert.equal(vad.silence(1000).ended, false, 'it was already over');
});

test('how long they have been talking is counted from the first sound of it', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    const seen = feed(vad, pcm(1000, speech()));
    const last = seen[seen.length - 1];
    // the onset is included: they were talking for it, it just was not believed yet
    assert.ok(last.speakingMs >= 960, `only counted ${last.speakingMs}ms of a second`);
});

test('a gap where nothing was transmitted does not teach it a new noise floor', () => {
    const vad = createVoiceActivity();
    feed(vad, pcm(1000, fan(4000)));
    const learned = vad.floor;
    assert.ok(learned > 0, 'the room was never heard at all');

    vad.silence(5000);
    assert.equal(vad.floor, learned, 'a client that stopped transmitting is not a quiet room');
});

// --- one person's turn, out of the pieces discord delivers it in ----------

function turn(options) {
    return createSpeechBuffer({ duckMs: 400, interruptMs: 3000, ...options });
}

/** Pushes a buffer in twenty-millisecond pieces on a clock that keeps up. */
function say(buffer, buf, clock, beaSpeaking = false) {
    const step = Math.round(20 * BYTES_PER_MS);
    const seen = [];
    for (let at = 0; at + step <= buffer.length; at += step) {
        clock.at += 20;
        seen.push(buf.push(buffer.subarray(at, at + step), { now: clock.at, beaSpeaking }));
    }
    return seen;
}

/** No packets for `ms`, checked as often as the sweep checks. */
function quiet(ms, buf, clock) {
    const seen = [];
    for (let elapsed = 0; elapsed < ms; elapsed += 100) {
        clock.at += 100;
        seen.push(buf.gap(clock.at));
    }
    return seen;
}

test('a sentence with a breath in it arrives as one turn, not two', () => {
    const clock = { at: 0 };
    const buf = turn();

    say(pcm(600, speech()), buf, clock);
    // discord closed the stream here and opened a new one; the turn did not end
    const during = quiet(300, buf, clock);
    assert.ok(!during.some((r) => r.ended), 'the breath was mistaken for the end');

    say(pcm(600, speech()), buf, clock);
    const after = quiet(HANGOVER_MS + 200, buf, clock);
    assert.ok(after.some((r) => r.ended), 'the turn never ended');

    const said = buf.take();
    assert.ok(said, 'a second of speech was thrown away as noise');
    assert.ok(said.ms > 1100, `both halves should be here, got ${said.ms}ms`);
});

test('a click is thrown away rather than transcribed', () => {
    const clock = { at: 0 };
    const buf = turn();

    say(pcm(80, keyboard()), buf, clock);
    quiet(HANGOVER_MS + 200, buf, clock);
    assert.equal(buf.take(), null);
});

test('a fan running for a minute never becomes a turn', () => {
    const clock = { at: 0 };
    const buf = turn();

    for (let i = 0; i < 20; i += 1) say(pcm(500, fan(9000)), buf, clock);
    assert.equal(buf.take(), null, 'the room was transcribed as if it had spoken');
});

test('a long enough overlap turns her down, a longer one stops her', () => {
    const clock = { at: 0 };
    const buf = turn();

    const seen = say(pcm(4000, speech()), buf, clock, true);
    const duckedAt = seen.findIndex((r) => r.duck);
    const stoppedAt = seen.findIndex((r) => r.interrupt);

    assert.ok(duckedAt > 0, 'she talked straight through somebody');
    assert.ok(stoppedAt > duckedAt, 'she never gave up the floor');
    assert.equal(seen.filter((r) => r.duck).length, 1, 'ducked more than once');
    assert.equal(seen.filter((r) => r.interrupt).length, 1, 'interrupted more than once');
    // 400ms and 3000ms, at twenty milliseconds a step
    assert.ok(Math.abs(duckedAt * 20 - 400) < 120, `ducked at ${duckedAt * 20}ms`);
    assert.ok(Math.abs(stoppedAt * 20 - 3000) < 120, `stopped at ${stoppedAt * 20}ms`);
});

test('a short "sì sì" turns her down and gives the floor straight back', () => {
    const clock = { at: 0 };
    const buf = turn();

    const seen = say(pcm(600, speech()), buf, clock, true);
    assert.ok(seen.some((r) => r.duck));
    assert.ok(!seen.some((r) => r.interrupt), 'agreeing with her is not interrupting her');

    const after = quiet(HANGOVER_MS + 200, buf, clock);
    assert.ok(after.some((r) => r.released), 'she never came back up');
});

test('a fan cannot accumulate its way to an interruption', () => {
    const clock = { at: 0 };
    const buf = turn();

    // six seconds of it: twice over the threshold, if loudness were the test
    const seen = say(pcm(6000, fan(12000)), buf, clock, true);
    assert.ok(!seen.some((r) => r.duck), 'a fan took the floor from her');
    assert.ok(!seen.some((r) => r.interrupt), 'a fan interrupted her');
});

test('something said over her is overheard; taking the floor is not', () => {
    const clock = { at: 0 };
    const short = turn();
    say(pcm(600, speech()), short, clock, true);
    quiet(HANGOVER_MS + 200, short, clock);
    assert.equal(short.take().overheard, true);

    const long = turn();
    say(pcm(4000, speech()), long, clock, true);
    quiet(HANGOVER_MS + 200, long, clock);
    const taken = long.take();
    assert.equal(taken.interrupted, true, 'they held the floor and she should know');

    const alone = turn();
    say(pcm(600, speech()), alone, clock, false);
    quiet(HANGOVER_MS + 200, alone, clock);
    assert.equal(alone.take().overheard, false, 'she was not even talking');
});

test('she is read fresh every chunk, not once when the stream opened', () => {
    const clock = { at: 0 };
    const buf = turn();

    // she starts talking a moment after they do, which is exactly the case the
    // old code got wrong: it had already decided, and decided on stale news
    say(pcm(100, speech()), buf, clock, false);
    const seen = say(pcm(3000, speech()), buf, clock, true);
    assert.ok(seen.some((r) => r.duck), 'nothing noticed her being talked over');
});

test('somebody who will not stop is sent on rather than held forever', () => {
    const clock = { at: 0 };
    const buf = turn({ maxTurnMs: 2000 });

    const seen = say(pcm(3000, speech()), buf, clock);
    assert.ok(seen.some((r) => r.ended), 'a monologue is buffered without limit');
    assert.ok(buf.take().ms <= 3000);
});

test('a turn cut for length does not duck her all over again', () => {
    const clock = { at: 0 };
    const buf = turn({ maxTurnMs: 1000 });

    const first = say(pcm(1200, speech()), buf, clock, true);
    assert.equal(first.filter((r) => r.duck).length, 1);
    assert.ok(first.some((r) => r.ended), 'the cut never came');
    buf.take();

    // they have not stopped talking, they were only cut off mid-sentence
    const rest = say(pcm(1200, speech()), buf, clock, true);
    assert.equal(rest.filter((r) => r.duck).length, 0, 'she was ducked twice for one overlap');
    assert.equal(rest.filter((r) => r.interrupt).length, 0, 'the brain was told twice');
});

test('what is kept is what gets sent: mono, sixteen kilohertz', () => {
    const clock = { at: 0 };
    const buf = turn();

    say(pcm(1000, speech()), buf, clock);
    quiet(HANGOVER_MS + 200, buf, clock);
    const said = buf.take();

    // a second of 16khz mono s16 is 32000 bytes; of 48khz stereo, 192000
    assert.ok(Math.abs(said.pcm.length - 32000) < 400, `kept ${said.pcm.length} bytes`);
});

test('a turn abandoned leaves nothing behind for the next one', () => {
    const clock = { at: 0 };
    const buf = turn();

    say(pcm(1000, speech()), buf, clock);
    buf.abandon();
    assert.equal(buf.open, false);
    assert.equal(buf.take(), null);
});

// --- the samples on the way out ------------------------------------------

test('the rate is dropped by averaging, not by throwing samples away', () => {
    // 16 khz is exactly the frequency that folds onto silence when two samples
    // in three are dropped; keeping one would let it through at full strength
    const fold = pcm(200, (t) => 10000 * Math.sin(2 * Math.PI * 16000 * t));
    const out = downsampleMono16k(fold);

    let peak = 0;
    for (let i = 0; i < out.length; i += 2) peak = Math.max(peak, Math.abs(out.readInt16LE(i)));
    assert.ok(peak < 1000, `a 16 khz tone came through at ${peak}`);
});

test('a voice survives the trip down to sixteen kilohertz', () => {
    const out = downsampleMono16k(pcm(200, speech()));
    let peak = 0;
    for (let i = 0; i < out.length; i += 2) peak = Math.max(peak, Math.abs(out.readInt16LE(i)));
    assert.ok(peak > 3000, `a voice came out at ${peak}`);
});

test('the wav header says what the file actually is', () => {
    const samples = downsampleMono16k(pcm(500, speech()));
    const wav = pcmToWav(samples);

    assert.equal(wav.subarray(0, 4).toString(), 'RIFF');
    assert.equal(wav.subarray(8, 12).toString(), 'WAVE');
    assert.equal(wav.readUInt32LE(4), wav.length - 8, 'the declared size is a lie');
    assert.equal(wav.readUInt16LE(22), 1, 'mono');
    assert.equal(wav.readUInt32LE(24), 16000);
    assert.equal(wav.readUInt32LE(40), samples.length, 'the declared data size is a lie');
});
