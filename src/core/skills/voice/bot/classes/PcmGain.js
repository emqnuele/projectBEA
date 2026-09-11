const { Transform } = require('stream');

const { SAMPLE_RATE, BYTES_PER_FRAME, BYTES_PER_MS } = require('./Pcm');

/**
 * volume, with a ramp, on the way to the player — plus a running count of what
 * actually got through.
 *
 * both halves matter. the ramp is what turns "she stops mid-word" into "she
 * trails off", which is what people do; the count is how the brain learns how
 * much of a sentence the room really heard, instead of assuming all of it.
 */
class PcmGain extends Transform {
    constructor(onProgress) {
        // one 20ms frame of read-ahead. the player pulls this stream as it
        // plays, so a small buffer is what keeps `playedMs` close to what the
        // room really heard — a fat one would report a sentence as finished
        // while a chunk of it is still sitting in memory
        super({ highWaterMark: BYTES_PER_FRAME * 960 });
        this.gain = 1;
        this.step = 0;
        this.framesLeft = 0;
        this.bytesOut = 0;
        this.onProgress = onProgress || (() => { });
        this.rest = Buffer.alloc(0);
        this.reportedMs = 0;
    }

    get playedMs() {
        return Math.round(this.bytesOut / BYTES_PER_MS);
    }

    // linear over `ms`: short enough to feel immediate, long enough not to click
    rampTo(target, ms) {
        const clamped = Math.max(0, Math.min(1, target));
        const frames = Math.max(1, Math.floor((ms / 1000) * SAMPLE_RATE));
        this.step = (clamped - this.gain) / frames;
        this.framesLeft = frames;
        this.target = clamped;
    }

    _transform(chunk, _enc, done) {
        const buffer = this.rest.length ? Buffer.concat([this.rest, chunk]) : chunk;
        const usable = buffer.length - (buffer.length % BYTES_PER_FRAME);
        // a subarray keeps a live view into `chunk`, which the stream owns and
        // may reuse for the next call; the leftover bytes must be copied out
        this.rest = Buffer.from(buffer.subarray(usable));

        const out = this.applyGain(buffer.subarray(0, usable));
        this.bytesOut += out.length;

        // ~every 250ms: often enough to act on, rare enough not to be chatter
        if (this.playedMs - this.reportedMs >= 250) {
            this.reportedMs = this.playedMs;
            this.onProgress(this.playedMs);
        }
        done(null, out);
    }

    applyGain(block) {
        // the common case is full volume with no ramp running: touch nothing
        if (this.gain === 1 && this.framesLeft === 0) return block;

        const out = Buffer.allocUnsafe(block.length);
        for (let i = 0; i < block.length; i += BYTES_PER_FRAME) {
            if (this.framesLeft > 0) {
                this.gain += this.step;
                this.framesLeft -= 1;
                if (this.framesLeft === 0) this.gain = this.target;
            }
            out.writeInt16LE(clamp16(block.readInt16LE(i) * this.gain), i);
            out.writeInt16LE(clamp16(block.readInt16LE(i + 2) * this.gain), i + 2);
        }
        return out;
    }
}

// clipping, not wrapping: a wrapped sample is a click, and a click sounds broken
function clamp16(value) {
    const rounded = Math.round(value);
    if (rounded > 32767) return 32767;
    if (rounded < -32768) return -32768;
    return rounded;
}

module.exports = { PcmGain, SAMPLE_RATE, BYTES_PER_FRAME, BYTES_PER_MS };
