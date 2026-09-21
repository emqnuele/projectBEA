import React from 'react';

/**
 * ATLASContextPanel — compact "current work" panel from ATLAS data.
 *
 * Answers:
 *  - "What project am I working on?"
 *  - "What tasks are active?"
 *  - "What milestone am I in?"
 *  - "What decisions matter here?"
 *
 * Reads from forgeState.atlas — never from any other source.
 * Empty state is graceful, not broken.
 */

function statusBadge(status) {
  const map = {
    active:    'bg-emerald-50 text-emerald-600 border-emerald-200/50',
    planning:  'bg-blue-50 text-blue-600 border-blue-200/50',
    paused:    'bg-amber-50 text-amber-600 border-amber-200/50',
    completed: 'bg-zinc-100 text-zinc-500 border-zinc-200/50',
    archived:  'bg-zinc-50 text-zinc-400 border-zinc-200/50',
    in_progress: 'bg-blue-50 text-blue-600 border-blue-200/50',
    todo:      'bg-zinc-50 text-zinc-500 border-zinc-200/50',
    backlog:   'bg-zinc-50 text-zinc-400 border-zinc-200/50',
    in_review: 'bg-violet-50 text-violet-600 border-violet-200/50',
    blocked:   'bg-red-50 text-red-600 border-red-200/50',
    done:      'bg-emerald-50 text-emerald-600 border-emerald-200/50',
    proposed:  'bg-zinc-50 text-zinc-500 border-zinc-200/50',
    finalized: 'bg-emerald-50 text-emerald-600 border-emerald-200/50',
    rejected:  'bg-red-50 text-red-600 border-red-200/50',
  };
  return map[status] || 'bg-zinc-50 text-zinc-500 border-zinc-200/50';
}

function statusLabel(status) {
  return status?.replace(/_/g, ' ') || 'unknown';
}

export default function ATLASContextPanel({ atlas }) {
  const activeProject = atlas?.active_project;
  const workItems = atlas?.recent_work_items ?? [];
  const milestones = atlas?.active_milestones ?? [];
  const decisions = atlas?.recent_decisions ?? [];

  // Filter work items to the ATLAS domain's active statuses
  // (WorkItemStatus: open, in_progress, blocked, completed, declined)
  const activeTasks = [...workItems]
    .filter(w => ['open', 'in_progress', 'blocked'].includes(w.status))
    .sort((a, b) => {
      const order = { in_progress: 0, open: 1, blocked: 2 };
      return (order[a.status] ?? 9) - (order[b.status] ?? 9);
    })
    .slice(0, 5);

  if (!activeProject) {
    return (
      <div className="flex flex-col h-full justify-center">
        <div className="text-[10px] uppercase tracking-wider text-zinc-400 mb-3">
          Current Work
        </div>
        <div className="flex flex-col items-center justify-center h-32 rounded-xl border border-dashed border-zinc-200/60">
          <svg className="w-8 h-8 text-zinc-300 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.5 14.25v-5.25a3.75 3.75 0 00-3.75-3.75h-1.5a3.75 3.75 0 00-3.75 3.75v5.25M19.5 14.25H4.5M19.5 14.25H16.5M16.5 14.25H12M12 14.25H9M9 14.25H4.5" />
          </svg>
          <div className="text-xs text-zinc-400">No project active</div>
          <div className="text-[10px] text-zinc-300 mt-0.5">Use /atlas/projects to create one</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Active project header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="text-[10px] uppercase tracking-wider text-zinc-400">
            Current Project
          </div>
        </div>
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${statusBadge(activeProject.status)}`}>
          {statusLabel(activeProject.status)}
        </span>
      </div>

      <div className="flex items-center gap-2 mb-3 px-2">
        <svg className="w-4 h-4 text-zinc-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <span className="text-sm font-semibold text-zinc-900 truncate">
          {activeProject.name}
        </span>
      </div>

      {/* Active tasks */}
      <div className="mb-2">
        <div className="text-[10px] uppercase tracking-wider text-zinc-400 mb-1.5 px-2">
          Active Tasks
        </div>
        {activeTasks.length === 0 ? (
          <div className="px-2 py-2 text-xs text-zinc-400 italic">No active tasks</div>
        ) : (
          <div className="space-y-1">
            {activeTasks.map(task => (
              <div key={task.item_id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-zinc-50/50 border border-zinc-100/50">
                <div className={`
                  w-1.5 h-1.5 rounded-full flex-shrink-0
                  ${task.status === 'in_progress' ? 'bg-blue-500'
                    : task.status === 'open' ? 'bg-zinc-300'
                    : task.status === 'blocked' ? 'bg-red-400'
                    : 'bg-zinc-200'}
                `} />
                <span className="flex-1 text-xs text-zinc-700 truncate">
                  {task.title}
                </span>
                <span className={`text-[10px] font-medium px-1 py-0.5 rounded border ${statusBadge(task.status)}`}>
                  {statusLabel(task.status)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Current milestone */}
      {milestones.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] uppercase tracking-wider text-zinc-400 mb-1.5 px-2">
            Current Milestone
          </div>
          <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-violet-50/30 border border-violet-100/30">
            <svg className="w-3.5 h-3.5 text-violet-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span className="flex-1 text-xs font-medium text-violet-800 truncate">
              {milestones[0].name}
            </span>
            {milestones[0].status !== 'completed' && (
              <span className="text-[10px] text-violet-500">active</span>
            )}
          </div>
        </div>
      )}

      {/* Recent decisions */}
      {decisions.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-400 mb-1.5 px-2">
            Recent Decisions
          </div>
          <div className="space-y-1">
            {decisions.slice(0, 2).map(d => (
              <div key={d.decision_id} className="flex items-start gap-2 px-2 py-1.5 rounded-lg bg-zinc-50/30 border border-zinc-100/30">
                <svg className="w-3 h-3 text-zinc-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-zinc-800 font-medium truncate">
                    {d.title}
                  </div>
                  <div className="text-[10px] text-zinc-400 mt-0.5">
                    {statusLabel(d.status)}
                    {d.decided_at ? ` · ${new Date(d.decided_at * 1000).toLocaleDateString()}` : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state for no tasks/milestones/decisions */}
      {activeTasks.length === 0 && milestones.length === 0 && decisions.length === 0 && (
        <div className="mt-2 px-2 text-xs text-zinc-400 italic">
          No tasks, milestones, or decisions yet
        </div>
      )}
    </div>
  );
}
