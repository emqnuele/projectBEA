import React from 'react';
import { mapPresentation } from './PresentationAdapter';

/**
 * SHURAPresenceDisplay — the visible SHURA presence element.
 *
 * Proves: "SHURA exists visually as a persistent presence."
 *
 * Combines:
 *  - PresentationAdapter (orb mode) for the visual
 *  - Text status line (speaking, listening, sleeping, dreaming, idle, etc.)
 *  - Emotion indicator
 *  - ATLAS project context badge (if active project exists)
 *
 * All visual properties derive from mapPresentation() — no inline magic numbers.
 */

const EMOTION_COLOR_MAP = {
  emerald:  'border-emerald-400 bg-emerald-50 text-emerald-700',
  blue:     'border-blue-400 bg-blue-50 text-blue-700',
  amber:    'border-amber-400 bg-amber-50 text-amber-700',
  violet:   'border-violet-400 bg-violet-50 text-violet-700',
  indigo:   'border-indigo-400 bg-indigo-50 text-indigo-700',
  slate:    'border-slate-400 bg-slate-50 text-slate-700',
  zinc:     'border-zinc-300 bg-zinc-50 text-zinc-600',
};

function emotionBorderColor(colorName) {
  return EMOTION_COLOR_MAP[colorName] || EMOTION_COLOR_MAP.zinc;
}

export default function SHURAPresenceDisplay({ forgeState }) {
  const presentation = mapPresentation(forgeState);

  if (!forgeState) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <div className="text-zinc-400 text-sm">Loading SHURA presence...</div>
      </div>
    );
  }

  const orbColorClass = emotionBorderColor(presentation.emotionColor);
  const isOffline = forgeState.is_connected === false;

  return (
    <div className="flex flex-col items-center justify-center h-full w-full px-6 py-8">
      {/* Avatar orb — PresentationAdapter output */}
      <div
        className={`
          relative flex items-center justify-center rounded-full
          transition-all duration-300 ease-out
          ${isOffline
            ? 'w-16 h-16 border-2 border-zinc-300 bg-zinc-100'
            : `w-20 h-20 border-2 ${orbColorClass.split(' ')[0]} bg-${presentation.emotionColor}-50`
          }
          ${presentation.speakingGlow === 'bright'
            ? 'shadow-[0_0_24px_8px_rgba(239,68,68,0.35)]'
            : 'shadow-md'
          }
          ${presentation.sleepingOpacity < 1 ? `opacity-${Math.round(presentation.sleepingOpacity * 100)}` : ''}
          ${presentation.motionScale !== 1.0 ? 'animate-pulse' : ''}
        `}
      >
        {/* Inner dot */}
        <div
          className={`
            w-8 h-8 rounded-full flex items-center justify-center text-sm
            ${isOffline
              ? 'bg-zinc-200 text-zinc-400'
              : `bg-${presentation.emotionColor}-500 text-white shadow-inner`
            }
          `}
        >
          {/* 3D model slot — placeholder for future SHURA model */}
          {presentation.mode === '3d' && forgeState.model_url ? (
            <div className="w-full h-full text-xs text-white/70">3D</div>
          ) : presentation.isConnected && !isOffline ? (
            <span className="text-lg font-bold">S</span>
          ) : (
            <span className="text-lg">●</span>
          )}
        </div>

        {/* Speaking glow ring */}
        {presentation.speakingGlow === 'bright' && (
          <div className="absolute inset-0 rounded-full border-2 border-transparent animate-ping">
            <div className="absolute inset-0 rounded-full border-2 border-red-400/50"></div>
          </div>
        )}
      </div>

      {/* Name + status */}
      <div className="mt-4 text-center">
        <div className="font-semibold text-sm text-zinc-900 tracking-tight">
          SHURA
        </div>
        <div className="mt-1.5 flex items-center justify-center gap-1.5">
          <span className="text-base">{presentation.statusEmoji}</span>
          <span className={`
            text-xs font-medium px-2 py-0.5 rounded-full
            ${isOffline
              ? 'bg-zinc-100 text-zinc-500'
              : presentation.statusLabel === 'speaking'
                ? 'bg-red-50 text-red-600'
                : presentation.statusLabel === 'listening'
                ? 'bg-emerald-50 text-emerald-600'
                : presentation.statusLabel === 'sleeping'
                ? 'bg-indigo-50 text-indigo-600'
                : presentation.statusLabel === 'dreaming'
                ? 'bg-violet-50 text-violet-600'
                : presentation.statusLabel === 'offline'
                ? 'bg-zinc-100 text-zinc-500'
                : 'bg-zinc-100 text-zinc-600'
            }
          `}>
            {presentation.statusLabel}
          </span>
        </div>
      </div>

      {/* Emotion */}
      {presentation.emotionLabel && presentation.emotionLabel !== 'present' && (
        <div className={`
          mt-2 text-xs font-medium px-2 py-0.5 rounded-full
          ${emotionBorderColor(presentation.emotionColor)}
        `}>
          {presentation.emotionLabel}
        </div>
      )}

      {/* ATLAS project badge */}
      {forgeState.atlas?.active_project && (
        <div className="mt-4 w-full max-w-[180px]">
          <div className="text-[10px] uppercase tracking-wider text-zinc-400 mb-1">
            Active Project
          </div>
          <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-700 bg-zinc-50 border border-zinc-200/50 rounded-lg px-2.5 py-1.5">
            <svg className="w-3.5 h-3.5 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span className="truncate">{forgeState.atlas.active_project.name}</span>
          </div>
        </div>
      )}

      {/* Offline indicator */}
      {isOffline && (
        <div className="mt-3 text-[10px] text-zinc-400 italic">
          Runtime disconnected
        </div>
      )}
    </div>
  );
}
