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

const {
    createVoiceActivity, HANGOVER_MS, ONSET_MS, MAX_VOICE_MS, FLOOR_WINDOW_MS,
} = require('../classes/VoiceActivity');
const { createSpeechBuffer } = require('../classes/SpeechBuffer');
const { createDownsampler, downsampleMono16k, pcmToWav, BYTES_PER_MS } = require('../classes/Pcm');

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
// of one — a real voice has formants that put even more of it inside the band.
// It stops for a consonant once a second, the one thing every real voice does
// and a record does not: measured on real speech, no two seconds go by without
// a dip under a tenth of its level.
const speech = (f0 = 140, amp = 6000) => (t) => {
    if (t % 1 >= 0.98) return 0;
    let value = 0;
    for (let h = 1; h <= 18; h += 1) value += (1 / h) * Math.sin(2 * Math.PI * f0 * h * t);
    return (amp * value) / 2;
};

const fan = (amp = 6000) => (t) => amp * (0.8 * Math.sin(2 * Math.PI * 70 * t)
    + 0.4 * Math.sin(2 * Math.PI * 140 * t) + 0.1 * (Math.random() * 2 - 1));

const hiss = (amp = 6000) => (t) => amp * Math.sin(2 * Math.PI * 9000 * t);

// steady, and sitting squarely in the speech band: music, a game, a television
// left on in the room. Every per-frame question answers "voice" about this.
const music = (amp = 4000) => (t) => amp * (Math.sin(2 * Math.PI * 400 * t)
    + 0.6 * Math.sin(2 * Math.PI * 600 * t) + 0.4 * Math.sin(2 * Math.PI * 900 * t));
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

test('somebody far from their microphone is heard, over a client that sends silence', () => {
    // about -47 dbfs: a whisper, a laptop across the desk, gain turned down
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    const seen = feed(vad, pcm(600, speech(160, 300)));
    assert.equal(vad.speaking, true, 'a quiet speaker never got a word in');
    const voiced = seen.reduce((sum, f) => sum + f.voicedMs + f.onsetVoicedMs, 0);
    assert.ok(voiced >= 500, `only ${voiced}ms of six tenths of a second counted as a voice`);
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

// a key, a beat, a cup put down: one frame loud, in the speech band
const tap = (amp = 9000) => (t) => amp * Math.sin(2 * Math.PI * 1500 * t);

test('typing after they finish does not hold their turn open', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, VOICE);

    // a key every 150ms, the way somebody types while the call goes on
    const seen = [];
    for (let i = 0; i < 20; i += 1) {
        seen.push(...feed(vad, pcm(20, tap())));
        seen.push(...feed(vad, pcm(140, silence())));
    }
    const endedAt = seen.findIndex((f) => f.ended);
    assert.ok(endedAt >= 0, 'the keys kept the turn open');
    assert.ok(endedAt * 20 <= HANGOVER_MS + 80, `ended ${endedAt * 20}ms after they stopped`);
});

test('a word that comes back just inside the hangover still belongs to the turn', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, VOICE);

    const pause = feed(vad, pcm(HANGOVER_MS - 40, silence()));
    const back = feed(vad, pcm(300, speech()));
    assert.ok(![...pause, ...back].some((f) => f.ended), 'the sentence was cut at its last breath');
    assert.equal(vad.speaking, true);
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

test('music in somebody\'s room does not hold the gate open for the whole call', () => {
    const vad = createVoiceActivity();
    // nothing to learn a floor from first: this is the case where the very
    // first packet anybody sends is already the thing that is not a voice
    const seen = feed(vad, pcm(MAX_VOICE_MS + 2000, music()));

    assert.ok(seen.some((f) => f.ended), 'it never let go');
    assert.equal(vad.speaking, false, 'the room is still holding the floor');
    assert.ok(vad.floor > 0, 'it let go without ever learning what the room sounds like');
});

test('a steady sound in the speech band lets go within seconds, not at the limit', () => {
    const vad = createVoiceActivity();
    // no room learned first: the first packet is already the record playing
    const seen = feed(vad, pcm(6000, music()));
    const endedAt = seen.findIndex((f) => f.ended) * 20;

    assert.ok(endedAt > 0, 'it never let go');
    assert.ok(endedAt <= FLOOR_WINDOW_MS + HANGOVER_MS + 200, `it held the floor for ${endedAt}ms`);
    assert.equal(seen.slice(endedAt / 20 + 1).filter((f) => f.started).length, 0,
        'the same sound was heard as a new voice');
});

test('the sound that held the floor too long does not take it again next frame', () => {
    const vad = createVoiceActivity();
    feed(vad, pcm(MAX_VOICE_MS + 2000, music()));

    const after = feed(vad, pcm(3000, music()));
    assert.ok(!after.some((f) => f.started), 'the same music was heard as a new voice');
});

test('the pauses inside a sentence are not a quieter room', () => {
    const vad = createVoiceActivity();
    const background = music(900);

    // the music has been on long enough for the gate to conclude it is the room
    feed(vad, pcm(MAX_VOICE_MS + 1000, background));
    assert.equal(vad.speaking, false, 'the music still has the floor');
    const learned = vad.floor;
    assert.ok(learned > 500, `the room was never learned, floor sat at ${learned}`);

    // somebody talks, and a sentence has silence in it — quieter than the room
    // has ever been, and not what the room sounds like
    for (let i = 0; i < 4; i += 1) {
        feed(vad, pcm(300, speech()));
        feed(vad, pcm(200, silence()));
    }
    assert.ok(vad.floor > learned / 2,
        `the gaps between words were learned as the room: ${vad.floor} from ${learned}`);

    // they stop, and the music is all that is left
    const after = feed(vad, pcm(3000, background));
    assert.ok(after.some((f) => f.ended),
        'the music kept the floor once the sentence over it had ended');
});

test('a voice too quiet to open the gate does not raise the bar it has to clear', () => {
    const vad = createVoiceActivity();
    feed(vad, pcm(1000, fan(300)));
    const room = vad.floor;

    // a murmur under the bar, still a voice and not the room
    const seen = feed(vad, pcm(600, speech(160, room * 3.5)));
    assert.ok(!seen.some((f) => f.started), 'the murmur was loud enough to start: the test is off');
    assert.ok(seen[seen.length - 1].level > room * 1.4, 'the murmur was quieter than the room: the test is off');
    assert.ok(vad.floor < room * 1.1, `a voice taught the room its level: ${room} -> ${vad.floor}`);
});

test('a room that gets louder while somebody talks is still learned from', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, VOICE);
    assert.equal(vad.speaking, true);

    // they keep the floor, but what arrives now has no voice in it
    feed(vad, pcm(2000, hiss(4000)));
    assert.ok(vad.floor > 1000, `the floor never followed the room, sat at ${vad.floor}`);
});

test('a voice still cannot raise the bar it is measured against', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    feed(vad, pcm(3000, speech()));
    assert.ok(vad.floor < 500, `a voice taught the gate its own level: ${vad.floor}`);
});

test('the hangover is not counted as somebody still talking', () => {
    const vad = createVoiceActivity();
    feed(vad, ROOM);
    const said = feed(vad, pcm(400, speech())).reduce((sum, f) => sum + f.voicedMs, 0);
    const waited = feed(vad, pcm(400, silence())).reduce((sum, f) => sum + f.voicedMs, 0);

    assert.ok(said >= 300, `only ${said}ms of four tenths of a second of speech`);
    assert.equal(waited, 0, 'the silence after it was counted as speech');
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

test('a one-word answer is a turn, not room noise', () => {
    const clock = { at: 0 };
    const buf = turn();

    // "yeah": a third of a second, the answer to half the questions she asks
    say(pcm(300, speech()), buf, clock);
    quiet(HANGOVER_MS + 200, buf, clock);
    const said = buf.take();
    assert.ok(said, 'the answer was thrown away as noise');
    // the frames it took to believe it were a voice too
    assert.ok(said.voicedMs >= 280, `only ${said.voicedMs}ms of three tenths of a second`);
});

test('"sì" is a turn, though only its vowel can be counted as a voice', () => {
    const clock = { at: 0 };
    const buf = turn();

    // the s sits above the speech band, where it looks exactly like hiss
    say(pcm(120, hiss(3000)), buf, clock);
    say(pcm(220, speech()), buf, clock);
    quiet(HANGOVER_MS + 200, buf, clock);
    assert.ok(buf.take(), 'the answer to her question never reached her');
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

test('music in the room cannot interrupt her', () => {
    const clock = { at: 0 };
    // the thresholds she ships with
    const buf = createSpeechBuffer({ duckMs: 400, interruptMs: 4000 });

    const seen = say(pcm(8000, music()), buf, clock, true);
    assert.ok(!seen.some((r) => r.interrupt), 'a song stopped her mid-sentence');
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

test('answering somebody already mid-sentence does not cut her off', () => {
    const clock = { at: 0 };
    const buf = turn();

    // they have been going for four seconds. She decides to answer, which is
    // what answering somebody looks like — the room does not go quiet first.
    say(pcm(4000, speech()), buf, clock, false);
    const seen = say(pcm(1000, speech()), buf, clock, true);

    assert.ok(!seen.some((r) => r.interrupt),
        'she was cut off for a second of overlap because they had started first');
});

test('the overlap is what stops her, and it is counted from when she started', () => {
    const clock = { at: 0 };
    const buf = turn();

    say(pcm(4000, speech()), buf, clock, false);
    const seen = say(pcm(3600, speech()), buf, clock, true);

    const stoppedAt = seen.findIndex((r) => r.interrupt);
    assert.ok(stoppedAt > 0, 'she never gave up the floor');
    assert.ok(Math.abs(stoppedAt * 20 - 3000) < 200,
        `stopped after ${stoppedAt * 20}ms of overlap, not 3000`);
});

test('each time she opens her mouth the count starts again', () => {
    const clock = { at: 0 };
    const buf = turn();

    // they lean on her, she stops, and they carry straight on talking
    const first = say(pcm(3600, speech()), buf, clock, true);
    assert.ok(first.some((r) => r.interrupt));

    say(pcm(2000, speech()), buf, clock, false);
    const second = say(pcm(1000, speech()), buf, clock, true);
    assert.ok(!second.some((r) => r.interrupt),
        'the next thing she said was cut off by an overlap that was already over');
});

test('short interjections do not add up to somebody taking the floor', () => {
    const clock = { at: 0 };
    const buf = turn();

    // "mh", "sì", a chair, a key: a tenth of a second at a time, with the
    // hangover holding the run open across every gap between them. Six seconds
    // of run, one second of anybody actually saying anything.
    const seen = [];
    for (let i = 0; i < 12; i += 1) {
        seen.push(...say(pcm(100, speech()), buf, clock, true));
        seen.push(...say(pcm(400, silence()), buf, clock, true));
    }
    assert.ok(!seen.some((r) => r.interrupt),
        'a second of sound spread over six stopped her');
});

test('she comes back up when she stops, not only when they do', () => {
    const clock = { at: 0 };
    const buf = turn();

    const over = say(pcm(800, speech()), buf, clock, true);
    assert.ok(over.some((r) => r.duck), 'she was never turned down');

    // she finished her sentence; they are still going
    const after = say(pcm(400, speech()), buf, clock, false);
    assert.ok(after.some((r) => r.released),
        'she stays ducked for as long as somebody keeps talking near her');
});

test('a turn carries what was said, not the room before it', () => {
    const clock = { at: 0 };
    const buf = turn();

    // the client transmits room tone for ten seconds before anybody speaks
    say(pcm(10000, silence()), buf, clock);
    say(pcm(1000, speech()), buf, clock);
    quiet(HANGOVER_MS + 200, buf, clock);

    const said = buf.take();
    assert.ok(said, 'the sentence was thrown away');
    assert.ok(said.ms < 2000, `${said.ms}ms of turn for a second of speech`);
});

test('the run-up to a word is kept, so the first consonant survives', () => {
    const clock = { at: 0 };
    const buf = turn();

    say(pcm(3000, silence()), buf, clock);
    say(pcm(1000, speech()), buf, clock);
    quiet(HANGOVER_MS + 200, buf, clock);

    const said = buf.take();
    assert.ok(said.ms > 1000, `nothing was kept from before the onset: ${said.ms}ms`);
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

/** The level of 16khz mono output, past the filter's ramp-in. */
function level(out, skipSamples = 200) {
    let sum = 0;
    let counted = 0;
    for (let i = skipSamples * 2; i + 1 < out.length; i += 2) {
        const sample = out.readInt16LE(i);
        sum += sample * sample;
        counted += 1;
    }
    return counted ? Math.sqrt(sum / counted) : 0;
}

const tone = (hz, amp = 12000) => (t) => amp * Math.sin(2 * Math.PI * hz * t);

test('nothing above eight kilohertz is folded down onto the speech', () => {
    // everything up there arrives somewhere under 8 khz when two samples in
    // three are thrown away, and 10 khz lands at 6: squarely on a voice
    const reference = level(downsampleMono16k(pcm(500, tone(1000))));

    for (const [hz, lands] of [[10000, 6000], [13000, 3000], [20000, 4000]]) {
        const folded = level(downsampleMono16k(pcm(500, tone(hz))));
        const down = 20 * Math.log10(Math.max(folded, 1e-9) / reference);
        assert.ok(down < -40,
            `${hz} Hz folded onto ${lands} Hz only ${(-down).toFixed(1)} dB down`);
    }
});

test('a voice survives the trip down to sixteen kilohertz', () => {
    const out = downsampleMono16k(pcm(200, speech()));
    let peak = 0;
    for (let i = 0; i < out.length; i += 2) peak = Math.max(peak, Math.abs(out.readInt16LE(i)));
    assert.ok(peak > 3000, `a voice came out at ${peak}`);
});

test('the speech band comes through at the level it went in at', () => {
    // it runs in front of a gate that reads levels: a resampler that quietly
    // changes the volume would move the threshold somebody has to clear
    for (const hz of [300, 1000, 3000]) {
        const before = level(pcm(500, tone(hz)), 0) / 1;
        const after = level(downsampleMono16k(pcm(500, tone(hz))));
        assert.ok(Math.abs(20 * Math.log10(after / before)) < 1,
            `${hz} Hz came out ${(20 * Math.log10(after / before)).toFixed(1)} dB off`);
    }
});

test('a stream filtered packet by packet is the same audio as one buffer', () => {
    // discord hands over twenty milliseconds at a time, and a filter restarted
    // at every packet puts a discontinuity into the audio fifty times a second
    const whole = pcm(500, speech());
    const atOnce = downsampleMono16k(whole);

    const downsample = createDownsampler();
    const step = Math.round(20 * BYTES_PER_MS);
    const pieces = [];
    for (let at = 0; at + step <= whole.length; at += step) {
        pieces.push(downsample(whole.subarray(at, at + step)));
    }
    const streamed = Buffer.concat(pieces);

    assert.equal(streamed.length, atOnce.length, 'a different number of samples came out');
    let worst = 0;
    for (let i = 0; i + 1 < streamed.length; i += 2) {
        worst = Math.max(worst, Math.abs(streamed.readInt16LE(i) - atOnce.readInt16LE(i)));
    }
    assert.ok(worst <= 1, `the packet boundaries moved samples by up to ${worst}`);
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

// --- the sweep runs between packets, the way it does in a call -------------

/** Packets every twenty milliseconds, with the sweep landing in between. */
function sayWhileSwept(buffer, buf, clock, beaSpeaking = false) {
    const step = Math.round(20 * BYTES_PER_MS);
    const seen = [];
    for (let at = 0; at + step <= buffer.length; at += step) {
        clock.at += 10;
        seen.push(buf.gap(clock.at, { beaSpeaking }));
        clock.at += 10;
        seen.push(buf.push(buffer.subarray(at, at + step), { now: clock.at, beaSpeaking }));
    }
    return seen;
}

/** No packets for `ms`, with the sweep looking every twenty. */
function quietlySwept(ms, buf, clock) {
    const seen = [];
    for (let elapsed = 0; elapsed < ms; elapsed += 20) {
        clock.at += 20;
        seen.push({ at: clock.at, report: buf.gap(clock.at) });
    }
    return seen;
}

test('the sweep between two packets does not wipe out being talked over', () => {
    const clock = { at: 0 };
    // production thresholds: the looser test ones pass a count that never reaches four seconds
    const buf = createSpeechBuffer({ duckMs: 400, interruptMs: 4000 });

    const seen = [];
    const step = Math.round(20 * BYTES_PER_MS);
    const talk = pcm(4400, speech());
    for (let at = 0; at + step <= talk.length; at += step) {
        clock.at += 10;
        seen.push({ at: clock.at, report: buf.gap(clock.at, { beaSpeaking: true }) });
        clock.at += 10;
        seen.push({ at: clock.at, report: buf.push(talk.subarray(at, at + step), { now: clock.at, beaSpeaking: true }) });
    }

    // every sweep used to count as a silence with her not speaking, which
    // zeroed the overlap: in a real call she was never ducked, never stopped
    assert.equal(seen.filter((s) => s.report.duck).length, 1, 'she was never turned down');
    const stopped = seen.filter((s) => s.report.interrupt);
    assert.equal(stopped.length, 1, 'she was never stopped');
    // four seconds of voice over her, after the onset that believes it is one;
    // the consonant each second before that point is not voice and is not counted
    const closures = 4 * 20;
    assert.ok(stopped[0].at >= ONSET_MS + 4000 + closures, `stopped after ${stopped[0].at}ms`);
    assert.ok(stopped[0].at <= ONSET_MS + 4000 + closures + 40, `stopped only after ${stopped[0].at}ms`);
});

test('the sweep between two packets does not end or hold up a turn', () => {
    const clock = { at: 0 };
    const buf = turn();

    const during = sayWhileSwept(pcm(1200, speech()), buf, clock);
    assert.ok(!during.some((r) => r.ended), 'a sweep between packets ended the turn');

    const lastPacket = clock.at;
    const after = quietlySwept(HANGOVER_MS + 200, buf, clock);
    const ended = after.find((s) => s.report.ended);
    assert.ok(ended, 'the turn never ended');
    // noticed within a frame of the hangover, not within a hundred milliseconds
    assert.ok(ended.at - lastPacket <= HANGOVER_MS + 20,
        `ended ${ended.at - lastPacket}ms after the last packet`);
    assert.ok(ended.at - lastPacket >= HANGOVER_MS - 20, 'the hangover was cut short');
    assert.ok(buf.take().ms > 1100);
});

// --- talked over by somebody who breathes -----------------------------------

// talking over her in bursts, with breaths that carry no packets at all
function talkOverInBursts(buf, clock, { bursts, burstMs, breathMs }) {
    const seen = [];
    for (let n = 0; n < bursts; n += 1) {
        seen.push(...sayWhileSwept(pcm(burstMs, speech()), buf, clock, true)
            .map((report) => ({ at: clock.at, report })));
        for (let quiet = 0; quiet < breathMs; quiet += 20) {
            clock.at += 20;
            seen.push({ at: clock.at, report: buf.gap(clock.at, { beaSpeaking: true }) });
        }
    }
    return seen;
}

test('a breath with no packets in it does not wipe out being talked over', () => {
    // the production thresholds, not the looser ones the other tests use
    const buf = createSpeechBuffer({ duckMs: 400, interruptMs: 4000 });
    const clock = { at: 0 };

    // a breath shorter than the hangover is part of the same run of talking
    const seen = talkOverInBursts(buf, clock, { bursts: 6, burstMs: 900, breathMs: 200 });

    assert.equal(seen.filter((s) => s.report.duck).length, 1, 'she was ducked more than once');
    assert.equal(seen.filter((s) => s.report.released).length, 0,
        'she came back up in the middle of somebody talking over her');
    const stopped = seen.filter((s) => s.report.interrupt);
    assert.equal(stopped.length, 1, 'five seconds of talking over her never stopped her');
});

test('a pause long enough to end their turn lets her back up', () => {
    const buf = createSpeechBuffer({ duckMs: 400, interruptMs: 4000 });
    const clock = { at: 0 };

    const seen = talkOverInBursts(buf, clock, { bursts: 1, burstMs: 900, breathMs: HANGOVER_MS + 100 });

    assert.equal(seen.filter((s) => s.report.duck).length, 1);
    assert.equal(seen.filter((s) => s.report.released).length, 1, 'she stayed turned down');
    assert.equal(seen.filter((s) => s.report.interrupt).length, 0);
});

function sweepAsked(isSpeaking, heardMs, playedAt, playbackDuration) {
    const VoiceManager = require('../classes/VoiceManager');
    const client = { user: { id: 'bot' }, channels: { cache: new Map() }, on() {} };
    const mgr = new VoiceManager(client);
    mgr.link.stop();
    mgr.link.send = () => true;

    const asked = [];
    const buffer = { gap: (now, opts) => { asked.push(opts); return { duck: false, interrupt: false, released: false, ended: false }; } };
    mgr.connections.set('g', {
        isSpeaking, heardMs, playedAt,
        speech: { resource: { playbackDuration }, playedBefore: 0 },
        speakers: new Map([['u', { buffer }]]),
    });

    mgr.sweep('g');
    return asked;
}

test('the sweep tells each turn whether she is speaking', () => {
    const asked = sweepAsked(true, 0, Date.now(), 20);
    assert.deepEqual(asked, [{ beaSpeaking: true }]);
});

test('the sweep does not call a starved line speaking', () => {
    // the player still says it is Playing, but nothing has reached the room
    // for longer than a packet: someone talking now is not talking over her
    const asked = sweepAsked(true, 20, Date.now() - 1000, 20);
    assert.deepEqual(asked, [{ beaSpeaking: false }]);
});
