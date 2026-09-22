import { create } from 'zustand';

/**
 * Central store for the Command Center.
 * Holds connection state, event feed, active surface, command palette visibility,
 * and any surface-specific shared state that doesn't belong to a single page.
 */
export const useStore = create((set, get) => ({
  // --- connection ---
  connection: 'connecting', // 'connecting' | 'online' | 'offline'
  streaming: false,

  // --- event feed ---
  events: [],
  pushEvent: (event) => {
    if (!event) return;
    set((state) => {
      if (state.events.some((e) => e.id === event.id)) return state;
      return { events: [event, ...state.events].slice(0, 500) };
    });
  },
  setEvents: (events) => set({ events }),

  // --- status ---
  status: null,
  setStatus: (status) => set({ status }),

  // --- active surface ---
  activeSurface: 'overview',
  setActiveSurface: (surface) => set({ activeSurface: surface }),

  // --- command palette ---
  paletteOpen: false,
  togglePalette: () => set((s) => ({ paletteOpen: !s.paletteOpen })),
  closePalette: () => set({ paletteOpen: false }),

  // --- sidebar ---
  sidebarCollapsed: localStorage.getItem('shura.sidebar.collapsed') === '1',
  toggleSidebar: () => {
    const next = !get().sidebarCollapsed;
    localStorage.setItem('shura.sidebar.collapsed', next ? '1' : '0');
    set({ sidebarCollapsed: next });
  },

  // --- theme ---
  theme: localStorage.getItem('shura.theme') || 'dark',
  toggleTheme: () => {
    const next = get().theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('shura.theme', next);
    document.documentElement.dataset.theme = next;
    set({ theme: next });
  },
}));
