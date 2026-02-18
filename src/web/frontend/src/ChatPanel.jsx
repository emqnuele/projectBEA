import { useState, useRef, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from './components/ui/card'
import { Button } from './components/ui/button'
import { Input } from './components/ui/input'
import { Separator } from './components/ui/separator'
import { Switch } from './components/ui/switch'
import { Label } from './components/ui/label'
import { useVAD } from './hooks/useVAD'

const API_BASE = 'http://localhost:8000'

export default function ChatPanel() {
    const [message, setMessage] = useState('')
    const [loading, setLoading] = useState(false)
    const [status, setStatus] = useState('')
    const [mode, setMode] = useState('manual') // 'manual' | 'auto'

    // api handlers

    const handleInterrupt = async () => {
        console.log("Interrupting AI...")
        try {
            await fetch(`${API_BASE}/interrupt`, { method: 'POST' })
            setStatus('Interrupted AI')
        } catch (e) {
            console.error("Interrupt Error:", e)
        }
    }

    const handleSend = async () => {
        if (!message.trim()) return
        setLoading(true)
        setStatus('Sending...')
        try {
            const res = await fetch(`${API_BASE}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            })
            if (res.ok) {
                setStatus('Message Sent!')
                setMessage('')
                setTimeout(() => setStatus(''), 2000)
            } else {
                setStatus('Error sending message')
            }
        } catch (e) {
            setStatus(`Error: ${e.message}`)
        } finally {
            setLoading(false)
        }
    }

    const sendAudio = async (blob) => {
        setLoading(true)
        setStatus('Uploading Audio...')
        const formData = new FormData()
        formData.append('file', blob, 'recording.wav')

        try {
            const res = await fetch(`${API_BASE}/audio`, {
                method: 'POST',
                body: formData
            })
            if (res.ok) {
                setStatus('Audio Sent!')
                setTimeout(() => setStatus(''), 2000)
            } else {
                setStatus('Error uploading audio')
            }
        } catch (e) {
            setStatus(`Error: ${e.message}`)
        } finally {
            setLoading(false)
        }
    }

    // vad hook
    const {
        startVAD,
        stopVAD,
        isListening,
        isSpeaking: isUserSpeaking,
        volume,
        recordingStatus
    } = useVAD({
        onSpeechStart: () => {
            // barge-in logic
            console.log("Speech Started: Triggering Interrupt")
            handleInterrupt()
        },
        onSpeechEnd: (audioBlob) => {
            console.log("Speech Ended: Sending Audio")
            sendAudio(audioBlob)
        }
    });

    // mode management
    useEffect(() => {
        if (mode === 'auto') {
            startVAD()
        } else {
            stopVAD()
        }
    }, [mode, startVAD, stopVAD])


    // manual recording logic
    const mediaRecorderRef = useRef(null)
    const audioChunksRef = useRef([])
    const [isManualRecording, setIsManualRecording] = useState(false)

    const startManualRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
            const mediaRecorder = new MediaRecorder(stream)
            mediaRecorderRef.current = mediaRecorder
            audioChunksRef.current = []

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) audioChunksRef.current.push(event.data)
            }

            mediaRecorder.start()
            setIsManualRecording(true)
            setStatus('Recording (Manual)...')
        } catch (e) {
            console.error(e)
        }
    }

    const stopManualRecording = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.stop()
            mediaRecorderRef.current.onstop = () => {
                const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' })
                sendAudio(audioBlob)
                // Stop tracks
                mediaRecorderRef.current.stream.getTracks().forEach(t => t.stop())
            }
            setIsManualRecording(false)
        }
    }

    // combine states
    const isRecording = isUserSpeaking || isManualRecording;

    return (
        <div className="max-w-xl mx-auto space-y-6">
            {/* Text Chat Card */}
            <Card className="shadow-md border-gray-100">
                <CardHeader className="pb-4">
                    <CardTitle className="text-lg">Text Chat</CardTitle>
                    <CardDescription>Type a message to the AI.</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex gap-2">
                        <Input
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            placeholder="Hello Brain..."
                            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                            disabled={loading || isRecording}
                            className="flex-1"
                        />
                        <Button
                            onClick={handleSend}
                            disabled={loading || isRecording}
                            className="bg-black hover:bg-gray-800 text-white"
                        >
                            Send
                        </Button>
                    </div>
                </CardContent>
            </Card>

            <div className="relative flex items-center justify-center py-4">
                <Separator className="absolute w-full" />
                <span className="relative bg-gray-50 px-2 text-xs text-gray-400 uppercase tracking-widest">OR</span>
            </div>

            {/* Audio Recorder Card */}
            <Card className="shadow-md border-gray-100 text-center py-10">
                <CardContent className="flex flex-col items-center justify-center gap-6">

                    {/* Mode Toggle */}
                    <div className="flex items-center space-x-2 absolute top-4 right-4 bg-gray-50 p-2 rounded-lg border border-gray-100">
                        <Label htmlFor="vad-mode" className={`text-xs ${mode === 'manual' ? 'font-bold text-black' : 'text-gray-400'}`}>Manual</Label>
                        <Switch
                            id="vad-mode"
                            checked={mode === 'auto'}
                            onCheckedChange={(c) => setMode(c ? 'auto' : 'manual')}
                        />
                        <Label htmlFor="vad-mode" className={`text-xs ${mode === 'auto' ? 'font-bold text-blue-600' : 'text-gray-400'}`}>Auto (VAD)</Label>
                    </div>

                    <div
                        className={`relative rounded-full transition-all duration-300 flex items-center justify-center cursor-pointer select-none
                        ${(isRecording || (mode === 'auto' && volume > 5)) ? 'w-36 h-36 bg-red-500/10 scale-105' : 'w-28 h-28 bg-gray-100 hover:bg-gray-200'}
                    `}
                        // Events only active in MANUAL mode
                        onMouseDown={mode === 'manual' ? startManualRecording : undefined}
                        onMouseUp={mode === 'manual' ? stopManualRecording : undefined}
                        onMouseLeave={mode === 'manual' ? stopManualRecording : undefined}
                        onTouchStart={mode === 'manual' ? startManualRecording : undefined}
                        onTouchEnd={mode === 'manual' ? stopManualRecording : undefined}
                    >
                        {/* Ring Animation / Volume Meter */}
                        {mode === 'auto' ? (
                            // Auto Mode Volume Ring
                            <div
                                className="absolute rounded-full border-2 border-blue-500 transition-all duration-75 opacity-50"
                                style={{
                                    width: `${Math.min(100 + volume * 4, 200)}%`,
                                    height: `${Math.min(100 + volume * 4, 200)}%`
                                }}
                            />
                        ) : (
                            // Manual Mode Recording Pulse
                            isRecording && (
                                <div className="absolute w-full h-full rounded-full border-4 border-red-500 animate-ping opacity-20"></div>
                            )
                        )}

                        <button
                            className={`w-20 h-20 rounded-full flex items-center justify-center transition-colors z-10
                            ${isRecording
                                    ? 'bg-red-500 text-white shadow-red-500/50 shadow-lg'
                                    : (mode === 'auto' ? 'bg-blue-600 text-white shadow-blue-500/50' : 'bg-white text-gray-800 shadow-sm border border-gray-200')
                                }
                        `}
                        >
                            {/* Icons */}
                            {mode === 'auto' ? (
                                // Wave/Listening Icon
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8">
                                    <path d="M12 2v20M2 12h20M7 9l-2 3 2 3M17 9l2 3-2 3" />
                                </svg>
                            ) : (
                                // Mic Icon
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8">
                                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                                    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                                    <line x1="12" x2="12" y1="19" y2="23" />
                                    <line x1="8" x2="16" y1="23" y2="23" />
                                </svg>
                            )}
                        </button>
                    </div>

                    <div className="space-y-1">
                        <h3 className={`text-lg font-semibold transition-colors ${isRecording ? 'text-red-500' : 'text-gray-900'}`}>
                            {mode === 'auto'
                                ? (isRecording ? 'Listening (Speaking)...' : (isListening ? 'Listening (Idle)...' : 'VAD Off'))
                                : (isRecording ? 'Recording...' : 'Hold to Speak')
                            }
                        </h3>
                        {mode === 'auto' && status && (
                            <p className="text-xs text-blue-500 animate-pulse">{status}</p>
                        )}
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
