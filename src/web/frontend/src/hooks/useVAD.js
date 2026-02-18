import { useState, useRef, useEffect, useCallback } from 'react';

// vad constants
const DEFAULT_VAD_THRESHOLD = 30;
const DEFAULT_SILENCE_DURATION = 1500;
const REQUIRED_SPEECH_FRAMES = 3;

export const useVAD = ({
    onSpeechStart,
    onSpeechEnd,
    threshold = DEFAULT_VAD_THRESHOLD,
    silenceDuration = DEFAULT_SILENCE_DURATION
} = {}) => {
    const [isListening, setIsListening] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [volume, setVolume] = useState(0);
    const [recordingStatus, setRecordingStatus] = useState('idle');

    const streamRef = useRef(null);
    const audioContextRef = useRef(null);
    const analyserRef = useRef(null);
    const mediaRecorderRef = useRef(null);
    const audioChunksRef = useRef([]);
    const vadIntervalRef = useRef(null);
    const silenceStartRef = useRef(null);

    // noise gate state
    const speechFramesRef = useRef(0);
    const isSpeakingRef = useRef(false);

    const startVAD = useCallback(async () => {
        if (isListening) return;

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;

            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            audioContextRef.current = audioContext;

            const analyser = audioContext.createAnalyser();
            analyser.fftSize = 256;
            analyserRef.current = analyser;

            const microphone = audioContext.createMediaStreamSource(stream);
            microphone.connect(analyser);

            const dataArray = new Uint8Array(analyser.frequencyBinCount);

            setIsListening(true);
            setRecordingStatus('listening');

            // reset state
            speechFramesRef.current = 0;

            // monitoring loop
            vadIntervalRef.current = setInterval(() => {
                analyser.getByteFrequencyData(dataArray);

                // calculate average volume
                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) {
                    sum += dataArray[i];
                }
                const avgVolume = sum / dataArray.length;
                setVolume(avgVolume);

                // logic
                if (avgVolume > threshold) {
                    // --- potential speech ---
                    speechFramesRef.current += 1;

                    if (speechFramesRef.current >= REQUIRED_SPEECH_FRAMES) {
                        // confirmed speech (sustained for ~90ms)
                        silenceStartRef.current = null; // reset silence timer

                        if (!isSpeakingRef.current) {
                            // rising edge: user started speaking
                            isSpeakingRef.current = true;
                            setIsSpeaking(true);
                            setRecordingStatus('recording');
                            if (onSpeechStart) onSpeechStart();

                            // start recording
                            startRecordingInternal(stream);
                        }
                    }
                } else {
                    // --- silence or brief noise ---
                    // if we haven't reached confirmation yet, reset the counter
                    if (!isSpeakingRef.current) {
                        speechFramesRef.current = 0;
                    }

                    if (isSpeakingRef.current) {
                        // user was speaking, now silent. check duration.
                        if (!silenceStartRef.current) {
                            silenceStartRef.current = Date.now();
                        } else {
                            if (Date.now() - silenceStartRef.current > silenceDuration) {
                                // falling edge: speech ended
                                isSpeakingRef.current = false;
                                speechFramesRef.current = 0; // reset frame counter
                                setIsSpeaking(false);
                                setRecordingStatus('listening');

                                stopRecordingInternal();
                            }
                        }
                    }
                }
            }, 30); // 30ms interval

        } catch (err) {
            console.error("VAD Setup Error:", err);
            setRecordingStatus('error');
        }
    }, [isListening, onSpeechStart, onSpeechEnd, threshold, silenceDuration]);

    const stopVAD = useCallback(() => {
        if (vadIntervalRef.current) clearInterval(vadIntervalRef.current);
        if (audioContextRef.current) audioContextRef.current.close();
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }

        setIsListening(false);
        setIsSpeaking(false);
        setRecordingStatus('idle');
        setVolume(0);
        isSpeakingRef.current = false;
    }, []);

    // internal recording helpers
    const startRecordingInternal = (stream) => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') return;

        const mediaRecorder = new MediaRecorder(stream);
        mediaRecorderRef.current = mediaRecorder;
        audioChunksRef.current = [];

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunksRef.current.push(event.data);
            }
        };

        mediaRecorder.start();
    };

    const stopRecordingInternal = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.stop();
            mediaRecorderRef.current.onstop = () => {
                const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
                if (audioBlob.size > 1000) {
                    if (onSpeechEnd) onSpeechEnd(audioBlob);
                }
            };
        }
    };

    // cleanup
    useEffect(() => {
        return () => {
            stopVAD();
        };
    }, []);

    return {
        startVAD,
        stopVAD,
        isListening,
        isSpeaking,
        volume,
        recordingStatus
    };
};
