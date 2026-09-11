/**
 * The microphone half of voice mode: open it, watch it, and hand over a take.
 *
 * Everything about *deciding* whether somebody is talking lives in
 * `voiceActivity.js`, which is pure and tested. This file owns only the parts
 * that need a browser — getUserMedia, an analyser, a MediaRecorder — and the
 * one trick that needs both:
 *
 * A recorder started once an onset is confirmed has already missed the first
 * syllable, because confirming it took ninety milliseconds of hearing it. So
 * recording starts on the *suspicion* of a voice and the take is thrown away if
 * the suspicion does not hold. The cost is a few discarded blobs a minute; what
 * it buys is that "hey" is no longer transcribed as "ey".
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { createVoiceActivity } from './voiceActivity.js';

// how often the spectrum is read. Well under the shortest thing worth hearing.
const FRAME_MS = 30;

const FFT_SIZE = 256;

// MediaRecorder does not produce WAV; take whatever this browser can make
const PREFERRED = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];

// under this, whatever was captured is a click and not a sentence
const MIN_TAKE_BYTES = 1000;

function extensionFor(mimeType) {
    if (mimeType.includes('ogg')) return 'ogg';
    if (mimeType.includes('mp4')) return 'm4a';
    return 'webm';
}

export const useVAD = ({ onSpeechStart, onSpeechEnd } = {}) => {
    const [isListening, setIsListening] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [volume, setVolume] = useState(0);
    const [recordingStatus, setRecordingStatus] = useState('idle');

    const streamRef = useRef(null);
    const audioContextRef = useRef(null);
    const mediaRecorderRef = useRef(null);
    const audioChunksRef = useRef([]);
    const tickRef = useRef(null);
    // set while a take is being kept; cleared when one is abandoned unheard
    const wantedRef = useRef(false);

    // --- recording, declared before the loop that drives it ---

    const startRecordingInternal = useCallback((stream) => {
        if (mediaRecorderRef.current?.state === 'recording') return;

        const mimeType = PREFERRED.find((type) => MediaRecorder.isTypeSupported(type)) || '';
        const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        mediaRecorderRef.current = recorder;
        audioChunksRef.current = [];

        recorder.ondataavailable = (event) => {
            if (event.data.size > 0) audioChunksRef.current.push(event.data);
        };
        recorder.start();
    }, []);

    const stopRecordingInternal = useCallback((keep) => {
        const recorder = mediaRecorderRef.current;
        if (!recorder || recorder.state === 'inactive') return;

        // attached before stop(), or the event can be missed
        recorder.onstop = () => {
            if (!keep) return;
            const type = recorder.mimeType || 'audio/webm';
            const blob = new Blob(audioChunksRef.current, { type });
            if (blob.size > MIN_TAKE_BYTES && onSpeechEnd) onSpeechEnd(blob, extensionFor(type));
        };
        recorder.stop();
    }, [onSpeechEnd]);

    const startVAD = useCallback(async () => {
        if (isListening) return;

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;

            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            audioContextRef.current = audioContext;

            const analyser = audioContext.createAnalyser();
            analyser.fftSize = FFT_SIZE;
            audioContext.createMediaStreamSource(stream).connect(analyser);

            const spectrum = new Uint8Array(analyser.frequencyBinCount);
            const vad = createVoiceActivity({
                sampleRate: audioContext.sampleRate,
                fftSize: FFT_SIZE,
            });

            setIsListening(true);
            setRecordingStatus('listening');
            wantedRef.current = false;

            tickRef.current = setInterval(() => {
                analyser.getByteFrequencyData(spectrum);
                const frame = vad.push(spectrum, performance.now());
                setVolume(frame.level);

                // a sound started: begin capturing it before knowing what it is
                if (frame.arming && mediaRecorderRef.current?.state !== 'recording') {
                    startRecordingInternal(stream);
                }

                if (frame.started) {
                    wantedRef.current = true;
                    setIsSpeaking(true);
                    setRecordingStatus('recording');
                    if (onSpeechStart) onSpeechStart();
                    return;
                }

                if (frame.ended) {
                    wantedRef.current = false;
                    setIsSpeaking(false);
                    setRecordingStatus('listening');
                    stopRecordingInternal(true);
                    return;
                }

                // it was a door, not a voice: drop the take rather than send it
                if (!frame.speaking && !frame.arming && !wantedRef.current
                    && mediaRecorderRef.current?.state === 'recording') {
                    stopRecordingInternal(false);
                }
            }, FRAME_MS);
        } catch (err) {
            console.error('VAD Setup Error:', err);
            setRecordingStatus('error');
        }
    }, [isListening, onSpeechStart, startRecordingInternal, stopRecordingInternal]);

    const stopVAD = useCallback(() => {
        if (tickRef.current) clearInterval(tickRef.current);
        // whatever was being captured when the microphone was closed was never
        // a finished sentence
        stopRecordingInternal(false);
        if (audioContextRef.current) audioContextRef.current.close();
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
        }

        setIsListening(false);
        setIsSpeaking(false);
        setRecordingStatus('idle');
        setVolume(0);
        wantedRef.current = false;
    }, [stopRecordingInternal]);

    // cleanup
    useEffect(() => () => stopVAD(), [stopVAD]);

    return {
        startVAD,
        stopVAD,
        isListening,
        isSpeaking,
        volume,
        recordingStatus,
    };
};
