import React, { useState, useEffect, useRef } from 'react';
import { Send, Mic, MicOff, Volume2, Info, ChevronDown, ChevronUp, Phone } from 'lucide-react';
import { useVAD } from '../hooks/useVAD';
import VoiceVisualizer from '../components/VoiceVisualizer';

// metadata viewer
function MetadataViewer({ data }) {
    const [isOpen, setIsOpen] = useState(false);

    // filter out standard fields
    const ignoredKeys = ['role', 'content', 'mood', 'timestamp', 'message', 'user_transcript'];
    const keys = Object.keys(data).filter(k => !ignoredKeys.includes(k));

    if (keys.length === 0) return null;

    return (
        <div className="mt-2 text-xs">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center gap-1 text-zinc-400 hover:text-zinc-600 transition-colors"
                title="Show Metadata"
            >
                <Info size={12} />
                <span className="font-medium">Details</span>
                {isOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>

            {isOpen && (
                <div className="mt-2 p-2 bg-zinc-50 rounded border border-zinc-100 font-mono text-[10px] text-zinc-600 space-y-1 overflow-x-auto">
                    {keys.map(key => (
                        <div key={key} className="flex flex-col">
                            <span className="font-bold text-zinc-400 capitalize">{key}:</span>
                            <span className="whitespace-pre-wrap">{JSON.stringify(data[key], null, 2)}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

export default function ChatPage() {
    const [input, setInput] = useState('');
    const [messages, setMessages] = useState([]);
    const [isRecording, setIsRecording] = useState(false); // manual recording state
    const [isLoading, setIsLoading] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);

    // auto mode vs manual mode
    const [mode, setMode] = useState('manual'); // 'manual' | 'auto'

    const messagesEndRef = useRef(null);
    const mediaRecorderRef = useRef(null);
    const audioChunks = useRef([]);

    // poll for showing status
    useEffect(() => {
        const interval = setInterval(async () => {
            try {
                const res = await fetch('http://localhost:8000/status');
                if (res.ok) {
                    const data = await res.json();
                    setIsSpeaking(data.is_speaking);
                }
            } catch (e) {
                // silent fail
            }
        }, 500);
        return () => clearInterval(interval);
    }, []);

    const refreshHistory = async () => {
        try {
            const res = await fetch('http://localhost:8000/history');
            if (res.ok) {
                const data = await res.json();
                setMessages(data);
            }
        } catch (e) {
            console.error("Failed to fetch history", e);
        }
    };

    useEffect(() => {
        refreshHistory();
    }, []);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);


    // vad integration
    const sendAudioBlob = async (audioBlob, placeholderContent = 'Audio Input...') => {
        const formData = new FormData();
        formData.append('file', audioBlob, 'recording.wav');

        const tempId = Date.now();
        const placeholderMsg = { role: 'user', content: placeholderContent, id: tempId };

        setMessages(prev => [...prev, placeholderMsg]);
        setIsLoading(true);

        try {
            const res = await fetch('http://localhost:8000/audio', {
                method: 'POST',
                body: formData
            });
            if (res.ok) {
                const data = await res.json();

                // update placeholder
                setMessages(prev => {
                    const list = [...prev];
                    const idx = list.findIndex(m => m.id === tempId);
                    if (idx !== -1) {
                        // replace content with transcript
                        list[idx] = {
                            ...list[idx],
                            content: data.response.user_transcript || "Audio Input"
                        };
                    }
                    // append ai response
                    return [...list, data.response];
                });
            }
        } catch (e) {
            console.error("Audio error", e);
            setMessages(prev => {
                const list = [...prev];
                const idx = list.findIndex(m => m.id === tempId);
                if (idx !== -1) {
                    list[idx] = { ...list[idx], content: "[Audio Failed]" };
                }
                return list;
            });
        } finally {
            setIsLoading(false);
        }
    };

    const {
        startVAD,
        stopVAD,
        isListening: isVADListening,
        isSpeaking: isUserSpeaking, // local user speaking
        volume
    } = useVAD({
        onSpeechStart: async () => {
            console.log("Speech Started (VAD) -> Interrupting");
            try {
                // interrupt
                await fetch('http://localhost:8000/interrupt', { method: 'POST' });
            } catch (e) { console.error(e); }
        },
        onSpeechEnd: (blob) => {
            console.log("Speech Ended (VAD) -> Sending Audio");
            sendAudioBlob(blob, 'Audio Input (Auto)...');
        },
        threshold: 20,
        silenceDuration: 1000
    });

    // handle mode switching
    useEffect(() => {
        if (mode === 'auto') {
            startVAD();
        } else {
            stopVAD();
        }
    }, [mode, startVAD, stopVAD]);


    const handleSend = async () => {
        if (!input.trim() || isLoading || isSpeaking) return;

        const userMsg = { role: 'user', content: input };
        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setIsLoading(true);

        try {
            const res = await fetch('http://localhost:8000/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: userMsg.content })
            });

            if (res.ok) {
                const data = await res.json();
                setMessages(prev => [...prev, data.response]);
            }
        } catch (e) {
            console.error("Chat error", e);
        } finally {
            setIsLoading(false);
        }
    };

    // manual recording
    const startManualRecording = async () => {
        if (isSpeaking) return;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            audioChunks.current = [];

            mediaRecorder.ondataavailable = (event) => {
                audioChunks.current.push(event.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks.current, { type: 'audio/wav' });
                sendAudioBlob(audioBlob, 'Audio Input (Manual)...');

                // stop tracks
                mediaRecorder.stream.getTracks().forEach(t => t.stop());
            };

            mediaRecorder.start();
            setIsRecording(true);
        } catch (e) {
            console.error("Mic error", e);
            alert("Microphone access denied or not available.");
        }
    };

    const stopManualRecording = () => {
        if (mediaRecorderRef.current && isRecording) {
            mediaRecorderRef.current.stop();
            setIsRecording(false);
        }
    };

    const toggleMode = () => {
        setMode(prev => prev === 'manual' ? 'auto' : 'manual');
    };

    return (
        <div className="flex flex-col h-full bg-white relative">

            {/* vad visualizer */}
            {mode === 'auto' && (
                <VoiceVisualizer
                    status={isSpeaking ? 'speaking' : isUserSpeaking ? 'recording' : 'idle'}
                    volume={volume}
                    isUserSpeaking={isUserSpeaking}
                />
            )}

            {/* show ai speaking */}
            {mode === 'manual' && isSpeaking && (
                <VoiceVisualizer status="speaking" volume={0} isUserSpeaking={false} />
            )}

            <div className="flex-1 overflow-y-auto px-4 md:px-20 py-8 space-y-6 flex flex-col">
                {messages.length === 0 && (
                    <div className="flex-1 flex flex-col items-center justify-center text-zinc-400 min-h-[50vh]">
                        <div className="bg-zinc-100 p-4 rounded-full mb-4">
                            <Mic size={24} className="text-zinc-400" />
                        </div>
                        <p>Start a conversation...</p>
                    </div>
                )}
                {messages.map((msg, idx) => {
                    const isUser = msg.role === 'user';
                    return (
                        <div key={idx} className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} animate-in`}>
                            <div
                                className={`max-w-[85%] md:max-w-[70%] px-5 py-3 rounded-2xl text-sm leading-relaxed shadow-sm
                        ${isUser
                                        ? 'bg-black text-white rounded-br-sm'
                                        : 'bg-zinc-100 text-zinc-800 border border-zinc-200 rounded-bl-sm'
                                    }`}
                            >
                                {!isUser && msg.mood && (
                                    <div className="text-[10px] uppercase font-bold text-zinc-500 mb-1 opacity-70">
                                        {msg.mood}
                                    </div>
                                )}
                                <p>{msg.content}</p>

                                {/* metadata */}
                                {!isUser && <MetadataViewer data={msg} />}
                            </div>
                        </div>
                    );
                })}
                <div ref={messagesEndRef} />
            </div>

            {/* footer / input area */}
            <div className="p-4 bg-white/80 backdrop-blur-md border-t border-zinc-100 z-10">
                {/* speaking indicator */}
                {isSpeaking && (
                    <div className="absolute top-[-40px] left-1/2 transform -translate-x-1/2 bg-zinc-900 text-white text-xs px-3 py-1.5 rounded-full flex items-center gap-2 shadow-sm animate-in fade-in slide-in-from-bottom-2">
                        <Volume2 size={12} className="animate-pulse" />
                        <span className="font-medium">AI is speaking...</span>
                    </div>
                )}

                <div className={`flex items-center gap-2 max-w-3xl mx-auto border rounded-full p-2 shadow-sm transition-all focus-within:ring-1 focus-within:ring-black focus-within:border-black
            ${isSpeaking ? 'bg-zinc-50 border-zinc-100 cursor-not-allowed opacity-80' : 'bg-white border-zinc-200'}
        `}>
                    {/* auto mode toggle */}
                    <button
                        onClick={toggleMode}
                        title={mode === 'auto' ? "Disable Voice Mode" : "Enable Voice Mode"}
                        className={`p-2.5 rounded-full transition-all duration-300 flex-shrink-0 flex items-center justify-center
                            ${mode === 'auto' ? 'bg-green-50 text-green-600' : 'text-zinc-400 hover:text-black hover:bg-zinc-50'}
                        `}
                    >
                        <Phone size={18} className={mode === 'auto' ? "fill-green-600" : ""} />
                    </button>

                    <button
                        onMouseDown={mode === 'manual' ? startManualRecording : undefined}
                        onMouseUp={mode === 'manual' ? stopManualRecording : undefined}
                        onMouseLeave={mode === 'manual' ? stopManualRecording : undefined}
                        disabled={isSpeaking || mode === 'auto'}
                        className={`p-2.5 rounded-full transition-all duration-300 flex-shrink-0
                ${isRecording
                                ? 'bg-red-50 text-red-500'
                                : isSpeaking
                                    ? 'text-zinc-300 cursor-not-allowed'
                                    : (mode === 'auto' ? 'text-zinc-300' : 'text-zinc-400 hover:text-black hover:bg-zinc-50')
                            }`}
                    >
                        {isRecording ? <MicOff size={20} className="animate-pulse" /> : <Mic size={20} />}
                    </button>

                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                        disabled={isLoading || isRecording || isSpeaking}
                        placeholder={isSpeaking ? "Wait for AI to finish..." : isRecording ? "Listening..." : (mode === 'auto' ? "Listening (Auto)..." : "Type your message...")}
                        className="flex-1 bg-transparent border-none outline-none focus:outline-none focus:ring-0 shadow-none text-zinc-900 placeholder-zinc-400 px-2 py-2 text-sm disabled:text-zinc-400"
                    />

                    <button
                        onClick={handleSend}
                        disabled={!input.trim() || isLoading || isSpeaking}
                        className="p-2.5 bg-black text-white rounded-full hover:bg-zinc-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <Send size={18} />
                    </button>
                </div>
                <div className="text-center mt-2">
                    <span className="text-[10px] text-zinc-300">AI Vtuber Engine</span>
                </div>
            </div>
        </div>
    );
}
