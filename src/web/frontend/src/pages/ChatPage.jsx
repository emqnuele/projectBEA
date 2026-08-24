import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
    ArrowDown, Check, ChevronDown, Copy, Mic, PhoneCall, PhoneOff, Send, Sparkles, Square,
} from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { clockTime } from '../lib/format';
import { useVAD } from '../hooks/useVAD';
import { useBrain } from '../state/BrainProvider';
import { useToast } from '../state/ToastProvider';
import { Glass } from '../components/glass/Glass';
import { IconButton } from '../components/ui/controls';
import { EmptyState } from '../components/ui/feedback';

const OPENERS = [
    'What are you doing right now?',
    'Who have you been talking to today?',
    'What do you want to do on stream?',
];

/** MediaRecorder does not produce WAV — send what it actually made. */
function pickRecordingType() {
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
    for (const type of candidates) {
        if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(type)) {
            return { type, extension: type.includes('ogg') ? 'ogg' : type.includes('mp4') ? 'm4a' : 'webm' };
        }
    }
    return { type: '', extension: 'webm' };
}

export default function ChatPage() {
    const [messages, setMessages] = useState(null);
    const [input, setInput] = useState('');
    const [thinking, setThinking] = useState(false);
    const [recording, setRecording] = useState(false);
    const [voiceMode, setVoiceMode] = useState(false);
    const [pinnedToBottom, setPinnedToBottom] = useState(true);

    const scrollerRef = useRef(null);
    const textareaRef = useRef(null);
    const recorderRef = useRef(null);
    const chunksRef = useRef([]);

    const toast = useToast();
    const { isSpeaking, status, interrupt } = useBrain();
    const sessionId = status?.session_id;

    const loadHistory = useCallback(async () => {
        try {
            setMessages(await api.history());
        } catch (e) {
            setMessages([]);
            toast.error('Could not load this conversation', e.message);
        }
    }, [toast]);

    useEffect(() => { loadHistory(); }, [loadHistory, sessionId]);

    // only follow the conversation when the reader is already at the bottom
    useEffect(() => {
        if (!pinnedToBottom) return;
        const scroller = scrollerRef.current;
        scroller?.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' });
    }, [messages, thinking, pinnedToBottom]);

    const onScroll = () => {
        const scroller = scrollerRef.current;
        if (!scroller) return;
        const distance = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
        setPinnedToBottom(distance < 120);
    };

    const growTextarea = () => {
        const node = textareaRef.current;
        if (!node) return;
        node.style.height = 'auto';
        node.style.height = `${Math.min(node.scrollHeight, 168)}px`;
    };

    useEffect(growTextarea, [input]);

    const send = async () => {
        const text = input.trim();
        if (!text || thinking) return;

        setMessages((prev) => [...(prev || []), {
            role: 'user', content: text, timestamp: new Date().toISOString(),
        }]);
        setInput('');
        setThinking(true);

        try {
            const data = await api.chat(text);
            const reply = data.response;
            if (reply?.content?.trim()) {
                setMessages((prev) => [...prev, reply]);
            } else {
                // she is allowed to say nothing — that is a real outcome, not a failure
                setMessages((prev) => [...prev, { role: 'silence', timestamp: new Date().toISOString() }]);
            }
        } catch (e) {
            toast.error('She did not answer', e.message);
            setMessages((prev) => [...prev, {
                role: 'failed', content: text, timestamp: new Date().toISOString(),
            }]);
        } finally {
            setThinking(false);
        }
    };

    const sendAudio = useCallback(async (blob, extension) => {
        const placeholder = { role: 'user', content: 'Transcribing…', pending: true, id: Date.now() };
        setMessages((prev) => [...(prev || []), placeholder]);
        setThinking(true);
        try {
            const data = await api.audio(blob, `recording.${extension}`);
            const reply = data.response;
            setMessages((prev) => {
                const list = prev.map((m) => (m.id === placeholder.id
                    ? { ...m, content: reply.user_transcript || 'Audio', pending: false }
                    : m));
                return reply?.content?.trim()
                    ? [...list, reply]
                    : [...list, { role: 'silence', timestamp: new Date().toISOString() }];
            });
        } catch (e) {
            toast.error('The audio did not go through', e.message);
            setMessages((prev) => prev.map((m) => (m.id === placeholder.id
                ? { ...m, content: 'Audio failed', pending: false, failed: true }
                : m)));
        } finally {
            setThinking(false);
        }
    }, [toast]);

    // --- voice mode: she listens continuously and you can talk over her ---
    const { startVAD, stopVAD, isSpeaking: userSpeaking, volume } = useVAD({
        onSpeechStart: () => { api.interrupt().catch(() => { }); },
        onSpeechEnd: (blob) => sendAudio(blob, 'wav'),
        threshold: 20,
        silenceDuration: 1000,
    });

    useEffect(() => {
        if (voiceMode) startVAD(); else stopVAD();
    }, [voiceMode, startVAD, stopVAD]);

    // --- push to talk: pointer events, so it works on a phone too ---
    const startRecording = async () => {
        if (voiceMode || recording) return;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const { type, extension } = pickRecordingType();
            const recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
            recorderRef.current = { recorder, extension };
            chunksRef.current = [];

            recorder.ondataavailable = (event) => chunksRef.current.push(event.data);
            recorder.onstop = () => {
                const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
                stream.getTracks().forEach((track) => track.stop());
                if (blob.size > 800) sendAudio(blob, extension);
            };
            recorder.start();
            setRecording(true);
        } catch (e) {
            toast.error('No microphone', e.message || 'The browser refused access to the microphone.');
        }
    };

    const stopRecording = () => {
        if (!recording) return;
        recorderRef.current?.recorder.stop();
        setRecording(false);
    };

    const placeholder = recording ? 'Listening…'
        : voiceMode ? 'Voice mode is on — just talk'
            : 'Say something to her';

    return (
        <div className="flex h-full flex-col gap-2.5">
            <Glass quiet className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-b3">
                <div
                    ref={scrollerRef}
                    onScroll={onScroll}
                    className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8"
                >
                    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
                        {messages === null && <ThinkingBubble label="Loading the conversation" />}

                        {messages?.length === 0 && (
                            <EmptyState icon={Sparkles} title="Nothing said yet">
                                She hears Discord, Twitch, Telegram and the game on her own. This is the
                                private line — what you say here comes from her owner.
                                <span className="mt-5 flex flex-wrap justify-center gap-2">
                                    {OPENERS.map((opener) => (
                                        <button
                                            key={opener}
                                            onClick={() => { setInput(opener); textareaRef.current?.focus(); }}
                                            className="rounded-full border border-line px-3 py-1.5 text-xs text-dim transition-colors hover:border-line-strong hover:text-text"
                                        >
                                            {opener}
                                        </button>
                                    ))}
                                </span>
                            </EmptyState>
                        )}

                        {messages?.map((message, index) => (
                            <Message key={message.id ?? index} message={message} />
                        ))}

                        <AnimatePresence>{thinking && <ThinkingBubble />}</AnimatePresence>
                    </div>
                </div>

                <AnimatePresence>
                    {!pinnedToBottom && (
                        <motion.button
                            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
                            onClick={() => { setPinnedToBottom(true); }}
                            className="glass-quiet absolute bottom-28 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-medium text-dim"
                        >
                            <ArrowDown size={12} /> Jump to the latest
                        </motion.button>
                    )}
                </AnimatePresence>
            </Glass>

            <Glass className="rounded-b3 p-2.5">
                {voiceMode && <VoiceMeter volume={volume} userSpeaking={userSpeaking} beaSpeaking={isSpeaking} />}

                <div className="flex items-end gap-2">
                    <IconButton
                        label={voiceMode ? 'Leave voice mode' : 'Enter voice mode — she listens continuously'}
                        variant={voiceMode ? 'vital' : 'ghost'}
                        onClick={() => setVoiceMode((v) => !v)}
                    >
                        {voiceMode ? <PhoneOff size={17} /> : <PhoneCall size={17} />}
                    </IconButton>

                    <IconButton
                        label="Hold to talk"
                        variant={recording ? 'danger' : 'ghost'}
                        disabled={voiceMode}
                        onPointerDown={startRecording}
                        onPointerUp={stopRecording}
                        onPointerCancel={stopRecording}
                        onKeyDown={(e) => { if (e.key === ' ' && !recording) { e.preventDefault(); startRecording(); } }}
                        onKeyUp={(e) => { if (e.key === ' ') { e.preventDefault(); stopRecording(); } }}
                        className={cn(recording && 'animate-[bea-pulse_1.2s_ease-in-out_infinite]')}
                    >
                        <Mic size={17} />
                    </IconButton>

                    <textarea
                        ref={textareaRef}
                        rows={1}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
                        }}
                        placeholder={placeholder}
                        aria-label="Message"
                        className="max-h-[168px] min-h-[38px] flex-1 resize-none bg-transparent px-1 py-2 text-[13px]
                                   leading-relaxed text-text outline-none placeholder:text-faint"
                    />

                    {isSpeaking && (
                        <IconButton
                            label="Stop her talking"
                            variant="vital"
                            onClick={() => interrupt().catch((e) => toast.error('Could not interrupt her', e.message))}
                        >
                            <Square size={13} className="fill-current" />
                        </IconButton>
                    )}

                    <IconButton
                        label="Send"
                        variant="primary"
                        onClick={send}
                        disabled={!input.trim() || thinking}
                    >
                        <Send size={16} />
                    </IconButton>
                </div>

                <p className="mt-1.5 px-1 text-[10px] text-faint">
                    Enter sends · Shift + Enter starts a line · hold the microphone to talk
                </p>
            </Glass>
        </div>
    );
}

function Message({ message }) {
    const [copied, setCopied] = useState(false);
    const [detailsOpen, setDetailsOpen] = useState(false);

    const extras = useMemo(() => {
        const ignored = ['role', 'content', 'mood', 'timestamp', 'message', 'user_transcript', 'id', 'pending', 'failed'];
        return Object.entries(message).filter(([key, value]) =>
            !ignored.includes(key) && value !== null && value !== '');
    }, [message]);

    if (message.role === 'silence') {
        return (
            <motion.p
                initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="self-center rounded-full border border-line px-3 py-1 text-[11px] text-faint"
            >
                She heard it and chose not to answer.
            </motion.p>
        );
    }

    const isUser = message.role === 'user' || message.role === 'failed';
    const failed = message.role === 'failed' || message.failed;

    const copy = async () => {
        await navigator.clipboard?.writeText(message.content || '');
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            className={cn('group flex flex-col gap-1', isUser ? 'items-end' : 'items-start')}
        >
            <div
                className={cn(
                    'max-w-[86%] rounded-b3 px-4 py-2.5 text-[13px] leading-relaxed sm:max-w-[74%]',
                    isUser
                        ? 'rounded-br-md bg-text text-bg'
                        : 'rounded-bl-md border border-line bg-fill-2 text-text',
                    message.pending && 'opacity-60',
                )}
                style={failed ? {
                    background: 'color-mix(in srgb, var(--flux-err) 12%, transparent)',
                    color: 'var(--flux-err)',
                } : undefined}
            >
                {!isUser && message.mood && (
                    <span className="mb-1 block font-mono text-[9px] uppercase tracking-widest opacity-60">
                        {message.mood}
                    </span>
                )}
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
            </div>

            <div className={cn(
                'flex items-center gap-2 px-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100',
                isUser ? 'flex-row-reverse' : 'flex-row',
            )}>
                <span className="tnum font-mono text-[10px] text-faint">{clockTime(message.timestamp)}</span>
                {message.content && (
                    <button
                        onClick={copy}
                        aria-label="Copy message"
                        className="text-faint transition-colors hover:text-text"
                    >
                        {copied ? <Check size={11} /> : <Copy size={11} />}
                    </button>
                )}
                {extras.length > 0 && (
                    <button
                        onClick={() => setDetailsOpen((v) => !v)}
                        className="flex items-center gap-0.5 text-[10px] text-faint transition-colors hover:text-text"
                    >
                        details
                        <ChevronDown size={10} className={cn('transition-transform', detailsOpen && 'rotate-180')} />
                    </button>
                )}
            </div>

            <AnimatePresence>
                {detailsOpen && (
                    <motion.dl
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="w-full max-w-[74%] overflow-hidden rounded-b2 border border-line bg-sunk p-3"
                    >
                        {extras.map(([key, value]) => (
                            <div key={key} className="border-b border-line py-1.5 last:border-0">
                                <dt className="font-mono text-[9px] uppercase tracking-wider text-faint">{key}</dt>
                                <dd className="mt-0.5 whitespace-pre-wrap break-words font-mono text-[11px] text-dim">
                                    {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
                                </dd>
                            </div>
                        ))}
                    </motion.dl>
                )}
            </AnimatePresence>
        </motion.div>
    );
}

function ThinkingBubble({ label = 'Thinking' }) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2.5 self-start rounded-b3 rounded-bl-md border border-line bg-fill-2 px-4 py-3"
        >
            <span className="flex items-end gap-[3px]">
                {[0, 1, 2].map((index) => (
                    <span
                        key={index}
                        className="h-3 w-[3px] origin-bottom rounded-full"
                        style={{
                            background: 'var(--flux-think)',
                            animation: `bea-bar 1s ease-in-out ${index * 0.14}s infinite`,
                        }}
                    />
                ))}
            </span>
            <span className="text-[12px] text-dim">{label}…</span>
        </motion.div>
    );
}

function VoiceMeter({ volume, userSpeaking, beaSpeaking }) {
    const level = Math.min(1, volume || 0);
    const state = beaSpeaking ? 'She is talking' : userSpeaking ? 'Hearing you' : 'Listening';
    const color = beaSpeaking ? 'var(--vital)' : userSpeaking ? 'var(--flux-act)' : 'var(--flux-mute)';

    return (
        <div className="mb-2.5 flex items-center gap-3 rounded-b2 border border-line bg-sunk px-3 py-2">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
            <span className="shrink-0 text-[11px] font-medium text-dim">{state}</span>
            <span className="h-1 flex-1 overflow-hidden rounded-full bg-fill-2">
                <motion.span
                    className="block h-full rounded-full"
                    style={{ background: color }}
                    animate={{ width: `${Math.max(4, level * 100)}%` }}
                    transition={{ duration: 0.12 }}
                />
            </span>
        </div>
    );
}
