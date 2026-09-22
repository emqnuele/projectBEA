import {
    Activity, Blocks, Brain, Bug, FolderArchive, Gauge, ListChecks,
    MessageSquare, Network, Users, Wrench,
} from 'lucide-react';

export const SURFACES = [
    { to: '/overview', end: true, label: 'Overview', icon: Gauge, hint: 'Everything at a glance' },
    { to: '/workspace', label: 'Workspace', icon: MessageSquare, hint: 'Active project and collaboration' },
    { to: '/memory', label: 'Memory', icon: Users, hint: 'What she remembers and who she knows' },
    { to: '/dream-studio', label: 'Dream Studio', icon: Brain, hint: 'Observe Dream lifecycle and state' },
    { to: '/agents', label: 'Agents', icon: ListChecks, hint: 'Active tasks and agent visibility' },
    { to: '/skills', label: 'Skills', icon: Blocks, hint: 'Skill registry and toggles' },
    { to: '/mcp', label: 'MCP / Tools', icon: Network, hint: 'Configured servers and tool inventory' },
    { to: '/artifacts', label: 'Artifacts', icon: FolderArchive, hint: 'Workspace files and artifacts' },
    { to: '/activity', label: 'Activity', icon: Activity, hint: 'Live event feed and audit trail' },
    { to: '/system', label: 'System', icon: Wrench, hint: 'Health, config, diagnostics' },
];

export const SETTINGS_SECTIONS = [
    { id: 'mind', label: 'Mind', hint: 'Language and the files behind her' },
    { id: 'provider', label: 'Provider', hint: 'API keys and the default model' },
    { id: 'voice', label: 'Voice', hint: 'How she sounds and where the audio goes' },
    { id: 'appearance', label: 'Appearance', hint: 'Theme, glass, motion' },
    { id: 'atlas', label: 'ATLAS', hint: 'Operational layer configuration' },
];

export const BRAND_ICON = Brain;

export const SHORTCUTS = {
    togglePalette: { key: 'k', ctrl: true, label: '⌘K' },
    toggleSidebar: { key: 'b', ctrl: true, label: '⌘B' },
    navOverview: { key: '1', ctrl: true, label: '⌘1' },
    navWorkspace: { key: '2', ctrl: true, label: '⌘2' },
    navMemory: { key: '3', ctrl: true, label: '⌘3' },
    navDreamStudio: { key: '4', ctrl: true, label: '⌘4' },
    navAgents: { key: '5', ctrl: true, label: '⌘5' },
    navSkills: { key: '6', ctrl: true, label: '⌘6' },
    navMcp: { key: '7', ctrl: true, label: '⌘7' },
    navArtifacts: { key: '8', ctrl: true, label: '⌘8' },
    navActivity: { key: '9', ctrl: true, label: '⌘9' },
    navSystem: { key: '0', ctrl: true, label: '⌘0' },
};
