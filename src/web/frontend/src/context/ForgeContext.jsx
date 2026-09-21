import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';

const FORGE_STATE_URL = '/forge/state';
const STATUS_URL = '/status';
const FULL_POLL_INTERVAL = 2000;   // ms — full semantic state
const LIGHT_POLL_INTERVAL = 500;   // ms — is_speaking / is_sleeping only

const ForgeContext = createContext(null);

export function useForgeState() {
  const ctx = useContext(ForgeContext);
  if (!ctx) throw new Error('useForgeState must be used inside <ForgeProvider>');
  return ctx;
}

export function ForgeProvider({ children, fullInterval = FULL_POLL_INTERVAL, lightInterval = LIGHT_POLL_INTERVAL }) {
  const [forgeState, setForgeState] = useState(null);
  const [lightState, setLightState] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const fetchInProgress = useRef(false);

  const fetchFullState = useCallback(async () => {
    if (fetchInProgress.current) return;
    fetchInProgress.current = true;
    try {
      const res = await fetch(FORGE_STATE_URL);
      if (!res.ok) throw new Error(`forge state fetch failed: ${res.status}`);
      const data = await res.json();
      setForgeState(data);
      setLastUpdated(Date.now());
      setError(null);
    } catch (e) {
      setError(e.message || 'Failed to fetch Forge state');
    } finally {
      fetchInProgress.current = false;
    }
  }, []);

  const fetchLightState = useCallback(async () => {
    try {
      const res = await fetch(STATUS_URL);
      if (res.ok) {
        const data = await res.json();
        setLightState(data);
      }
    } catch (e) {
      // Light state is best-effort; don't spam errors
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchFullState();
    fetchLightState();
    setIsLoading(false);
  }, [fetchFullState, fetchLightState]);

  // Polling intervals
  useEffect(() => {
    const fullTimer = setInterval(fetchFullState, fullInterval);
    const lightTimer = setInterval(fetchLightState, lightInterval);
    return () => {
      clearInterval(fullTimer);
      clearInterval(lightTimer);
    };
  }, [fetchFullState, fetchLightState, fullInterval, lightInterval]);

  const refetch = useCallback(() => {
    fetchFullState();
    fetchLightState();
  }, [fetchFullState, fetchLightState]);

  // Merge light state into forge state for live signals, and project the
  // flat backend ForgeState into the nested view-shape (plan Step 3.1):
  //   { presence: {...}, atlas: {...}, dream: {...}, activity: {...} }
  // Flat fields are preserved so presence components can consume either.
  const state = forgeState ? {
    ...forgeState,
    // Nested view groups (derived from the same flat ForgeState — no extra fetch)
    presence: {
      state: forgeState.presence_state,
      is_connected: forgeState.is_connected,
      emotion: forgeState.emotion,
      motion: forgeState.motion,
      is_speaking: lightState?.is_speaking ?? forgeState.is_speaking ?? false,
      is_sleeping: lightState?.is_sleeping ?? forgeState.is_sleeping ?? false,
      is_dreaming: forgeState.is_dreaming,
    },
    atlas: {
      active_project: forgeState.active_project,
      recent_work_items: forgeState.recent_work_items,
      active_milestones: forgeState.active_milestones,
      recent_decisions: forgeState.recent_decisions,
    },
    dream: { dream_state: forgeState.dream_state },
    activity: { recent_events: forgeState.recent_events },
    // Live signals from /status (faster poll) overlay the full state
    is_speaking: lightState?.is_speaking ?? forgeState.is_speaking ?? false,
    is_sleeping: lightState?.is_sleeping ?? forgeState.is_sleeping ?? false,
    active_skills: lightState?.active_skills ?? forgeState.active_skills ?? [],
  } : null;

  const value = {
    state,
    isLoading,
    error,
    lastUpdated,
    refetch,
  };

  return (
    <ForgeContext.Provider value={value}>
      {children}
    </ForgeContext.Provider>
  );
}
