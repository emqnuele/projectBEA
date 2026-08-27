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
    { id: 'engine', label: 'Provider', hint: 'Keys and the default model' },
    { id: 'models', label: 'Models', hint: 'Which models think for her, and how fast' },
    { id: 'attention', label: 'Attention', hint: 'What wakes her and what she lets pass' },
    { id: 'rhythm', label: 'Initiative', hint: 'When she starts something herself' },
    { id: 'discord', label: 'Discord', hint: 'Voice, DMs and who she listens to' },
    { id: 'telegram', label: 'Telegram', hint: 'Groups, DMs, photos and voice notes' },
    { id: 'twitch', label: 'Twitch', hint: 'Chat, raids and subs' },
    { id: 'voice', label: 'Voice', hint: 'How she sounds and where the audio goes' },
    { id: 'hearing', label: 'Hearing', hint: 'How speech becomes text' },
    { id: 'stream', label: 'Stream', hint: 'OBS, the avatar and the text bubble' },
    { id: 'world', label: 'Minecraft', hint: 'Her body on the server' },
    { id: 'donations', label: 'Donations', hint: 'The webhook that tells her about money' },
    { id: 'appearance', label: 'Appearance', hint: 'Theme, glass and motion' },
];

export const BRAND_ICON = BrainCircuit;
export const VERSION = 'v2.0';
