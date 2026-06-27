import React from 'react';
import { Mic } from 'lucide-react';

export default function VoiceVisualizer({ status, volume, isUserSpeaking }) {
    // status: 'idle', 'listening', 'recording', 'processing', 'speaking'

    // Helper to determine visual state
    const isRecording = status === 'recording' || isUserSpeaking;
    const isProcessing = status === 'processing';
    const isSpeaking = status === 'speaking'; // AI Speaking

    return (
        <div className="fixed bottom-24 right-8 z-50 flex items-center justify-center pointer-events-none select-none">
            {/* orb container */}
            <div className="relative flex items-center justify-center w-20 h-20">

                {/* core orb */}
                <div
                    className={`w-12 h-12 rounded-full flex items-center justify-center transition-all duration-300 shadow-lg border
                        ${isSpeaking ? 'bg-zinc-900 border-zinc-900 scale-110 shadow-zinc-900/10' :
                            isRecording ? 'bg-emerald-50 border-emerald-250 scale-110 shadow-sm' :
                                isProcessing ? 'bg-purple-50 border-purple-200 animate-pulse scale-95' :
                                    'bg-white border-zinc-200/80'}
                    `}
                    style={{
                        transform: isRecording ? `scale(${1 + Math.min(volume, 1) * 0.4})` : undefined
                    }}
                >
                    {isSpeaking ? (
                        // music bars
                        <div className="flex gap-0.5 h-3.5 items-center justify-center">
                            <div className="w-0.5 bg-white animate-[music-bar_0.4s_ease-in-out_infinite]" />
                            <div className="w-0.5 bg-white animate-[music-bar_0.5s_ease-in-out_infinite_0.1s]" />
                            <div className="w-0.5 bg-white animate-[music-bar_0.6s_ease-in-out_infinite_0.2s]" />
                            <div className="w-0.5 bg-white animate-[music-bar_0.5s_ease-in-out_infinite_0.3s]" />
                        </div>
                    ) : (
                        <Mic
                            size={20}
                            className={`transition-colors duration-300 
                                ${isRecording ? 'text-emerald-600' :
                                    isProcessing ? 'text-purple-600' : 'text-zinc-400'}
                            `}
                        />
                    )}
                </div>
            </div>

            <style>{`
                @keyframes music-bar {
                    0%, 100% { height: 20%; }
                    50% { height: 100%; }
                }
            `}</style>
        </div>
    );
}

