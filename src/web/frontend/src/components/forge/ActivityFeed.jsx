import React from 'react';

/**
 * ActivityFeed — compact event timeline from ForgeState.
 *
 * Shows recent events from forgeState.activity.recent_events.
 * Color-coded by event type. Limited to last 20 (matches backend limit).
 * Empty state is "No recent activity".
 */

const EVENT_TYPE_STYLES = {
  // Speech (presence/events.py: speech.*)
  'speech.started':    { color: 'text-emerald-600', bg: 'bg-emerald-50/40', icon: '💬' },
  'speech.finished':   { color: 'text-emerald-500', bg: 'bg-emerald-50/20', icon: '💬' },
  'speech.interrupted':{ color: 'text-red-400',     bg: 'bg-red-50/20',     icon: '✖️' },
  // Tool (presence/events.py: tool.*)
  'tool.started':      { color: 'text-blue-600',   bg: 'bg-blue-50/40',   icon: '🔧' },
  'tool.completed':    { color: 'text-blue-500',   bg: 'bg-blue-50/20',   icon: '🔧' },
  'tool.progress':     { color: 'text-blue-400',   bg: 'bg-blue-50/10',   icon: '🔧' },
  'tool.failed':       { color: 'text-red-500',    bg: 'bg-red-50/30',    icon: '⚠️' },
  // Dream (dream lifecycle events)
  'dream.started':     { color: 'text-violet-600', bg: 'bg-violet-50/40', icon: '🌙' },
  'dream.completed':   { color: 'text-violet-500', bg: 'bg-violet-50/20', icon: '🌙' },
  'dream.snapshot':    { color: 'text-violet-400', bg: 'bg-violet-50/10', icon: '🌙' },
  // Presence (presence/events.py: presence.*)
  'presence.connected':    { color: 'text-emerald-500', bg: 'bg-emerald-50/20', icon: '🔌' },
  'presence.disconnected': { color: 'text-red-400',    bg: 'bg-red-50/20',    icon: '🔌' },
  'presence.state.changed':{ color: 'text-zinc-500',   bg: 'bg-zinc-50/20',   icon: '🔄' },
  // STT / Input (presence/events.py: input.*)
  'input.listening.started':  { color: 'text-amber-500', bg: 'bg-amber-50/30', icon: '🎤' },
  'input.listening.finished': { color: 'text-amber-400', bg: 'bg-amber-50/10', icon: '🎤' },
  'input.transcript.final':   { color: 'text-amber-500', bg: 'bg-amber-50/20', icon: '📝' },
  // Agent turn (presence/events.py: agent.turn.*)
  'agent.turn.started':   { color: 'text-zinc-600', bg: 'bg-zinc-50/30', icon: '🤖' },
  'agent.turn.completed': { color: 'text-zinc-500', bg: 'bg-zinc-50/20', icon: '🤖' },
  'agent.turn.failed':    { color: 'text-red-500',  bg: 'bg-red-50/30',  icon: '⚠️' },
  // ATLAS (atlas/models.py AtlasEventType: atlas.*)
  'atlas.project.created':        { color: 'text-blue-500',   bg: 'bg-blue-50/20',   icon: '📁' },
  'atlas.project.updated':        { color: 'text-blue-400',   bg: 'bg-blue-50/10',   icon: '📁' },
  'atlas.project.active_changed': { color: 'text-blue-500',   bg: 'bg-blue-50/20',   icon: '📁' },
  'atlas.work_item.created':      { color: 'text-blue-400',   bg: 'bg-blue-50/10',   icon: '📋' },
  'atlas.work_item.transitioned': { color: 'text-blue-500',   bg: 'bg-blue-50/20',   icon: '📋' },
  'atlas.milestone.created':      { color: 'text-violet-400', bg: 'bg-violet-50/10', icon: '🏁' },
  'atlas.milestone.completed':    { color: 'text-violet-500', bg: 'bg-violet-50/20', icon: '🏁' },
  'atlas.decision.recorded':      { color: 'text-violet-400', bg: 'bg-violet-50/10', icon: '🗳️' },
  'atlas.artifact.added':         { color: 'text-violet-400', bg: 'bg-violet-50/10', icon: '📦' },
  // System
  config_updated:    { color: 'text-zinc-500',   bg: 'bg-zinc-50/20',   icon: '⚙️' },
  // Default
  default: { color: 'text-zinc-400', bg: 'bg-zinc-50/20', icon: '●' },
};

function styleForEventType(eventType) {
  if (!eventType) return EVENT_TYPE_STYLES.default;
  return EVENT_TYPE_STYLES[eventType] || EVENT_TYPE_STYLES.default;
}

function formatTimestamp(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  } catch {
    return '';
  }
}

function eventMessage(event) {
  // Prefer a concise label from event_type; fall back to message field
  if (event.event_type) {
    // Event types use dot-notation ("agent.turn.started") with underscore
    // words ("work_item"); split on both, then title-case.
    const parts = event.event_type.split(/[._]/);
    return parts.map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(' ');
  }
  if (event.message) {
    return event.message.substring(0, 60);
  }
  return 'event';
}

export default function ActivityFeed({ events }) {
  const eventList = events ?? [];
  const recent = eventList.slice(0, 20).reverse(); // most recent first

  if (recent.length === 0) {
    return (
      <div className="flex flex-col h-full justify-center">
        <div className="text-[10px] uppercase tracking-wider text-zinc-400 mb-3 px-2">
          Activity
        </div>
        <div className="flex flex-col items-center justify-center h-24 rounded-xl border border-dashed border-zinc-200/60">
          <div className="text-xs text-zinc-400">No recent activity</div>
          <div className="text-[10px] text-zinc-300 mt-0.5">Events will appear here</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="text-[10px] uppercase tracking-wider text-zinc-400 mb-3 px-2">
        Activity
      </div>
      <div className="flex-1 overflow-y-auto space-y-0.5 pr-1">
        {recent.map((event, idx) => {
          const style = styleForEventType(event.event_type);
          const ts = formatTimestamp(event.timestamp);
          return (
            <div
              key={event.event_id || idx}
              className={`flex items-center gap-2 px-2 py-1.5 rounded-lg transition-colors ${style.bg}`}
            >
              <span className="text-xs flex-shrink-0">{style.icon}</span>
              <span className={`flex-1 text-xs font-medium ${style.color} truncate`}>
                {eventMessage(event)}
              </span>
              {ts && (
                <span className="text-[10px] text-zinc-400 flex-shrink-0 tabular-nums">
                  {ts}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
