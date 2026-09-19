// what discord plays and the only thing the brain sends: 48khz stereo s16le
const SAMPLE_RATE = 48000;
const CHANNELS = 2;
const BYTES_PER_FRAME = CHANNELS * 2; // 2 channels * 2 bytes
const BYTES_PER_MS = (SAMPLE_RATE * BYTES_PER_FRAME) / 1000;

// what speech-to-text is given: mono, 16khz, which is all any of them use
const STT_RATE = 16000;
const DECIMATION = SAMPLE_RATE / STT_RATE; // 3

/**
 * The low-pass in front of the decimation, as a windowed sinc.
 *
 * Throwing two samples in three away folds everything above 8 khz back down
 * under it, so whatever is up there arrives on top of the speech. What was
 * here before was an average of the three, which is a three-tap filter: it has
 * a null at exactly 16 and 32 khz and almost nothing anywhere else, so a tone
 * at 10 khz still landed at 6 khz only 5.9 dB down, and one at 13 khz landed
 * at 3 khz 12 dB down. Speech has little up there. A call has a game in it, or
 * music, or a cymbal, or the hiss of a cheap microphone, and all of that was
 * being folded into the band the transcriber reads.
 *
 * 63 taps and a Hamming window: the cut starts under 7 khz and everything past
 * 8 is 50 dB down or better, which is the whole point. Built here rather than
 * written out as a table so the numbers that describe it stay readable.
 */
const CUTOFF_HZ = 6600;
const TAPS = 63;

const LOWPASS = (() => {
    const taps = new Float64Array(TAPS);
    const middle = (TAPS - 1) / 2;
    const omega = (2 * Math.PI * CUTOFF_HZ) / SAMPLE_RATE;
    let total = 0;
    for (let i = 0; i < TAPS; i += 1) {
        const n = i - middle;
        const sinc = n === 0 ? omega : Math.sin(omega * n) / n;
        const window = 0.54 - 0.46 * Math.cos((2 * Math.PI * i) / (TAPS - 1));
        taps[i] = sinc * window;
        total += taps[i];
    }
    // unity at dc: a filter that quietly changes the volume is a filter with a
    // bug in it, and this one runs in front of a noise gate that reads levels
    for (let i = 0; i < TAPS; i += 1) taps[i] /= total;
    return taps;
})();

/**
 * 48khz stereo -> 16khz mono, filtered, one speaker's stream at a time.
 *
 * Stateful because the stream is: discord hands over twenty milliseconds at a
 * time, and a filter restarted at every packet puts a discontinuity into the
 * audio fifty times a second. The tail of each packet is what the next one
 * starts from.
 */
function createDownsampler() {
    const history = new Float64Array(TAPS - 1);

    return function downsample(pcm) {
        const frames = Math.floor(pcm.length / BYTES_PER_FRAME);
        // one mono sample per frame, behind everything the last packet left
        const samples = new Float64Array(history.length + frames);
        samples.set(history, 0);
        for (let f = 0; f < frames; f += 1) {
            const at = f * BYTES_PER_FRAME;
            samples[history.length + f] =
                (pcm.readInt16LE(at) + pcm.readInt16LE(at + 2)) / 2;
        }

        const out = Buffer.alloc(Math.floor(frames / DECIMATION) * 2);
        let wrote = 0;
        // only at the samples that survive: the ones thrown away never need
        // filtering, which is two thirds of the work not done
        for (let centre = 0; centre + TAPS <= samples.length; centre += DECIMATION) {
            let sum = 0;
            for (let t = 0; t < TAPS; t += 1) sum += samples[centre + t] * LOWPASS[t];
            if (wrote + 2 > out.length) break;
            out.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(sum))), wrote);
            wrote += 2;
        }

        history.set(samples.subarray(samples.length - history.length));
        return wrote === out.length ? out : out.subarray(0, wrote);
    };
}

/** The same thing for a buffer that arrives whole, with nothing before it. */
function downsampleMono16k(pcm) {
    return createDownsampler()(pcm);
}

/** A 44-byte canonical WAV header in front of raw samples. */
function pcmToWav(pcm, sampleRate = STT_RATE, numChannels = 1) {
    const header = Buffer.alloc(44);
    const byteRate = sampleRate * numChannels * 2;

    header.write('RIFF', 0);
    header.writeUInt32LE(36 + pcm.length, 4);
    header.write('WAVE', 8);

    header.write('fmt ', 12);
    header.writeUInt32LE(16, 16);
    header.writeUInt16LE(1, 20); // pcm, uncompressed
    header.writeUInt16LE(numChannels, 22);
    header.writeUInt32LE(sampleRate, 24);
    header.writeUInt32LE(byteRate, 28);
    header.writeUInt16LE(numChannels * 2, 32);
    header.writeUInt16LE(16, 34);

    header.write('data', 36);
    header.writeUInt32LE(pcm.length, 40);

    return Buffer.concat([header, pcm]);
}

module.exports = {
    SAMPLE_RATE,
    CHANNELS,
    BYTES_PER_FRAME,
    BYTES_PER_MS,
    STT_RATE,
    CUTOFF_HZ,
    createDownsampler,
    downsampleMono16k,
    pcmToWav,
};
