import React, { useState, useRef } from 'react';
import { motion } from 'framer-motion';
import { useForgeState, ForgeProvider } from '../context/ForgeContext';
import SHURAPresenceDisplay from '../components/forge/SHURAPresenceDisplay';
import ATLASContextPanel from '../components/forge/ATLASContextPanel';
import ActivityFeed from '../components/forge/ActivityFeed';

/**
 * ForgePage — the Forge vertical slice.
 *
 * Proves the complete loop:
 *   user interaction → SHURA runtime → event/state change → Forge projection
 *   → visible SHURA response
 *
 * Layout:
 *  - Left: SHURAPresenceDisplay (avatar + status + emotion + project badge)
 *  - Right: ATLASContextPanel (current project, tasks, milestones, decisions)
 *  - Bottom: ActivityFeed (recent events, live-updating)
 *  - Chat input at bottom: sends message via /chat, proves the interaction loop
 */

function ForgePageContent() {
  const { state, isLoading, error } = useForgeState();
  const [chatMessage, setChatMessage] = useState('');
  const chatInputRef = useRef(null);

  const handleSendMessage = async () => {
    const msg = chatMessage.trim();
    if (!msg) return;
    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      });
      if (res.ok) {
        setChatMessage('');
        chatInputRef.current?.focus();
      }
    } catch (e) {
      console.error('Failed to send chat message', e);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col h-full w-full">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-zinc-400 text-sm animate-pulse">Loading Forge...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col h-full w-full">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-red-500 text-sm">
            Forge connection error: {error}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-full bg-white">
      {/* Main grid: presence (left) + ATLAS context (right) */}
      <div className="flex-1 flex gap-4 px-4 py-4 min-h-0">
        {/* Left: SHURA presence */}
        <div className="w-[220px] flex-shrink-0">
          <div className="h-full rounded-xl border border-zinc-200/60 bg-zinc-50/30 overflow-hidden">
            <SHURAPresenceDisplay forgeState={state} />
          </div>
        </div>

        {/* Right: ATLAS context + activity */}
        <div className="flex-1 flex flex-col gap-3 min-w-0">
          {/* ATLAS context panel */}
          <div className="flex-1 min-h-0">
            <div className="h-full rounded-xl border border-zinc-200/60 bg-white overflow-hidden">
              <ATLASContextPanel atlas={state?.atlas} />
            </div>
          </div>

          {/* Activity feed */}
          <div className="h-[160px] flex-shrink-0">
            <div className="h-full rounded-xl border border-zinc-200/60 bg-white overflow-hidden">
              <ActivityFeed events={state?.activity?.recent_events} />
            </div>
          </div>
        </div>
      </div>

      {/* Chat input — interaction loop entry point */}
      <div className="flex-shrink-0 border-t border-zinc-200/40 px-4 py-2 bg-white">
        <form
          onSubmit={(e) => { e.preventDefault(); handleSendMessage(); }}
          className="flex items-center gap-2 max-w-2xl"
        >
          <input
            ref={chatInputRef}
            type="text"
            value={chatMessage}
            onChange={(e) => setChatMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message SHURA..."
            className="
              flex-1 px-3 py-2 text-sm border border-zinc-200/60 rounded-lg
              bg-zinc-50/50 text-zinc-900 placeholder-zinc-400
              focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-zinc-300
              transition-all
            "
            disabled={!state?.is_connected}
          />
          <button
            type="submit"
            disabled={!chatMessage.trim() || !state?.is_connected}
            className="
              px-3 py-2 rounded-lg text-sm font-medium
              bg-zinc-900 text-white disabled:opacity-40 disabled:cursor-not-allowed
              hover:bg-zinc-800 transition-colors
            "
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}

export default function ForgePage() {
  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex-shrink-0 px-4 py-2 border-b border-zinc-200/40 bg-white">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m0 0V3.75m0 0a6.01 6.01 0 00-1.5-.189m1.5.189A6.01 6.01 0 0112 3.75m-8.25 8.25h16.5" />
          </svg>
          <span className="text-sm font-semibold text-zinc-900">Forge</span>
          <span className="text-[10px] text-zinc-400 ml-1">— SHURA presence workspace</span>
        </div>
      </div>
      <ForgeProvider>
        <ForgePageContent />
      </ForgeProvider>
    </div>
  );
}
