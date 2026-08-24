// The dashboard is served by the brain itself, so calls go to its own origin.
// A hardcoded localhost:8000 broke the moment the server moved host or port.
// In `npm run dev` there is no backend on the vite origin, so point at the default.
export const API_BASE =
    import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? 'http://localhost:8000' : '');
