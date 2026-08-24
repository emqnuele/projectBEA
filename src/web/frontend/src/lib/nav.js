import {
    Activity, Blocks, BrainCircuit, Gauge, ListChecks, MessageSquare, Users,
} from 'lucide-react';

export const NAV = [
    { to: '/dashboard', end: true, label: 'Overview', icon: Gauge, hint: 'Everything at a glance' },
    { to: '/dashboard/chat', label: 'Talk', icon: MessageSquare, hint: 'Your own conversation with her' },
    { to: '/dashboard/plan', label: 'Today', icon: ListChecks, hint: "The stream's objectives" },
    { to: '/dashboard/activity', label: 'Activity', icon: Activity, hint: 'What she is perceiving and doing' },
    { to: '/dashboard/memory', label: 'Memory', icon: Users, hint: 'Who she knows and what she remembers' },
    { to: '/dashboard/skills', label: 'Abilities', icon: Blocks, hint: 'What she is able to do' },
];

export const SETTINGS_SECTIONS = [
    { id: 'mind', label: 'Mind', hint: 'Persona, language and the files behind her' },
    { id: 'engine', label: 'Model', hint: 'Which model thinks for her' },
    { id: 'voice', label: 'Voice', hint: 'How she sounds and where the audio goes' },
    { id: 'hearing', label: 'Hearing', hint: 'How speech becomes text' },
    { id: 'stream', label: 'Stream', hint: 'OBS, the avatar and the text bubble' },
    { id: 'channels', label: 'Channels', hint: 'Discord, Telegram, Twitch, donations' },
    { id: 'world', label: 'Minecraft', hint: 'Her body on the server' },
    { id: 'appearance', label: 'Appearance', hint: 'Theme, glass and motion' },
];

export const BRAND_ICON = BrainCircuit;
export const VERSION = 'v2.0';
