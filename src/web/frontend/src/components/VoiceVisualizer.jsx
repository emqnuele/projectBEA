import React from 'react';
import { Mic, Activity } from 'lucide-react';

export default function VoiceVisualizer({ status, volume, isUserSpeaking }) {
    // status: 'idle', 'listening', 'recording', 'processing', 'speaking'

    // Helper to determine visual state
    const isRecording = status === 'recording' || isUserSpeaking;
    const isProcessing = status === 'processing';
    const isSpeaking = status === 'speaking'; // AI Speaking

    return (
        <div className="fixed bottom-24 right-8 z-50 flex items-center justify-center pointer-events-none">
            {/* orb container */}
            <div className="relative flex items-center justify-center w-20 h-20">

                {/* ping rings */}
                {!isProcessing && !isSpeaking && (
                    <>
                        <div className="absolute inset-0 bg-blue-500/10 rounded-full animate-ping" style={{ animationDuration: '3s' }} />
                        <div className="absolute inset-0 bg-blue-500/10 rounded-full animate-ping" style={{ animationDuration: '2s', animationDelay: '0.5s' }} />
                    </>
                )}

                {/* core orb */}
                <div
                    className={`w-14 h-14 rounded-full flex items-center justify-center transition-all duration-300 shadow-2xl backdrop-blur-md
                        ${isSpeaking ? 'bg-zinc-900 scale-110 shadow-zinc-900/50' :
                            isRecording ? 'bg-blue-600 scale-110 shadow-blue-600/50' :
                                isProcessing ? 'bg-indigo-400 animate-pulse scale-95' :
                                    'bg-white/80 border border-zinc-200 shadow-lg'}
                    `}
                    style={{
                        transform: isRecording ? `scale(${1 + Math.min(volume, 1) * 0.5})` : undefined
                    }}
                >
                    {isSpeaking ? (
                        // music bars
                        <div className="flex gap-0.5 h-4 items-center justify-center">
                            <div className="w-0.5 bg-white animate-[music-bar_0.4s_ease-in-out_infinite]" />
                            <div className="w-0.5 bg-white animate-[music-bar_0.5s_ease-in-out_infinite_0.1s]" />
                            <div className="w-0.5 bg-white animate-[music-bar_0.6s_ease-in-out_infinite_0.2s]" />
                            <div className="w-0.5 bg-white animate-[music-bar_0.5s_ease-in-out_infinite_0.3s]" />
                        </div>
                    ) : (
                        <Mic
                            size={24}
                            className={`transition-colors duration-300 
                                ${isRecording ? 'text-white' :
                                    isProcessing ? 'text-white/80' : 'text-zinc-400'}
                            `}
                        />
                    )}
                </div>

                {/* status label */}
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
