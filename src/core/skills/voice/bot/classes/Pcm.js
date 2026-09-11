// what discord plays and the only thing the brain sends: 48khz stereo s16le
const SAMPLE_RATE = 48000;
const CHANNELS = 2;
const BYTES_PER_FRAME = CHANNELS * 2; // 2 channels * 2 bytes
const BYTES_PER_MS = (SAMPLE_RATE * BYTES_PER_FRAME) / 1000;

// what speech-to-text is given: mono, 16khz, which is all any of them use
const STT_RATE = 16000;
const DECIMATION = SAMPLE_RATE / STT_RATE; // 3

/**
 * 48khz stereo -> 16khz mono.
 *
 * The three frames in each group are averaged rather than one of them kept.
 * That average is a three-tap filter with a null exactly at 16 and 32 khz —
 * the two frequencies that fold onto DC when you throw away two samples in
 * three. Keeping one sample instead folds every hiss, click and cymbal in the
 * top of the band straight down into the range the transcriber is reading.
 */
function downsampleMono16k(pcm) {
    const groupBytes = BYTES_PER_FRAME * DECIMATION;
    const out = Buffer.alloc(Math.floor(pcm.length / groupBytes) * 2);
    let at = 0;
    for (let i = 0; i + groupBytes <= pcm.length; i += groupBytes) {
        let sum = 0;
        for (let f = 0; f < DECIMATION; f += 1) {
            const frame = i + f * BYTES_PER_FRAME;
            sum += pcm.readInt16LE(frame) + pcm.readInt16LE(frame + 2);
        }
        out.writeInt16LE(Math.round(sum / (DECIMATION * CHANNELS)), at);
        at += 2;
    }
    return out;
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
    downsampleMono16k,
    pcmToWav,
};
