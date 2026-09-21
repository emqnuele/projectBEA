import React from 'react';

/**
 * PresentationAdapter — semantic state → visual presentation props.
 *
 * This is the replaceable boundary between Forge's semantic state and whatever
 * renders SHURA visually. It does NOT import any renderer (no Three.js, no
 * Live2D, no avatar library). It emits abstract presentation props that a
 * rendering component interprets.
 *
 * Modes:
 *  - "orb"  : CSS/SVG presence indicator. Default. Extensible.
 *  - "3d"   : Placeholder for SHURA 3D model. Not implemented yet.
 *
 * The adapter never knows about the backend. It is pure presentation logic.
 */

// Emotion → color mapping for orb mode
const EMOTION_COLORS = {
  calm:       'emerald',
  peaceful:   'emerald',
  serene:     'emerald',
  focused:    'blue',
  thinking:   'blue',
  concerned:  'amber',
  serious:    'amber',
  thoughtful: 'amber',
  excited:    'violet',
  energetic:  'violet',
  curious:    'violet',
  happy:      'violet',
  sad:        'indigo',
  melancholy: 'indigo',
  tired:      'slate',
  neutral:    'zinc',
  default:    'zinc',
};

const EMOTION_DESCRIPTIONS = {
  calm:       'calm',
  peaceful:   'peaceful',
  serene:     'serene',
  focused:    'focused',
  thinking:   'thinking',
  concerned:  'concerned',
  serious:    'serious',
  thoughtful: 'thoughtful',
  excited:    'excited',
  energetic:  'energetic',
  curious:    'curious',
  happy:      'happy',
  sad:        'sad',
  melancholy: 'melancholy',
  tired:      'tired',
  neutral:    'neutral',
  default:    'present',
};

function emotionToColor(emotion) {
  if (!emotion || emotion === 'none' || emotion === 'default') return 'zinc';
  const key = emotion.toLowerCase();
  return EMOTION_COLORS[key] || 'zinc';
}

function emotionToDescription(emotion) {
  if (!emotion || emotion === 'none' || emotion === 'default') return 'present';
  const key = emotion.toLowerCase();
  return EMOTION_DESCRIPTIONS[key] || emotion;
}

function deriveStatusLabel(state) {
  if (!state) return 'present';
  if (state.is_speaking) return 'speaking';
  if (state.presence_state === 'listening') return 'listening';
  if (state.is_sleeping) return 'sleeping';
  if (state.is_dreaming) return 'dreaming';
  if (state.is_connected === false) return 'offline';
  if (state.presence_state === 'idle') return 'idleing';
  if (state.presence_state === 'busy') return 'busy';
  if (state.presence_state === 'thinking') return 'thinking';
  return 'present';
}

function deriveStatusEmoji(state) {
  if (!state) return '●';
  if (state.is_speaking) return '💬';
  if (state.presence_state === 'listening') return '🎤';
  if (state.is_sleeping) return '😴';
  if (state.is_dreaming) return '🌙';
  if (state.is_connected === false) return '🔌';
  if (state.presence_state === 'busy') return '💭';
  if (state.presence_state === 'thinking') return '🤔';
  return '●';
}

/**
 * mapPresentation — pure function. No side effects. No React dependencies.
 */
export function mapPresentation(forgeState, options = {}) {
  const { mode = 'orb', modelUrl = null } = options;

  if (mode === '3d') {
    // Placeholder for when the SHURA 3D model is ready.
    // The model URL would come from configuration, not from state.
    return {
      mode: '3d',
      modelUrl: modelUrl || null,
      expressionHint: emotionToDescription(forgeState?.emotion),
      isSpeaking: forgeState?.is_speaking ?? false,
      isSleeping: forgeState?.is_sleeping ?? false,
      // These would drive the 3D model's position/rotation/expression
      // when a renderer is attached. Currently no-op.
      poseHint: 'idle',
    };
  }

  // Default: "orb" mode
  const emotion = forgeState?.emotion;
  const isSpeaking = forgeState?.is_speaking ?? false;
  const isSleeping = forgeState?.is_sleeping ?? false;
  const motion = forgeState?.motion;
  const isDreaming = forgeState?.is_dreaming ?? false;

  return {
    mode: 'orb',
    // Orb appearance
    emotionColor: emotionToColor(emotion),
    emotionLabel: emotionToDescription(emotion),
    speakingGlow: isSpeaking || isDreaming ? 'bright' : 'none',
    sleepingOpacity: isSleeping ? 0.35 : 1.0,
    motionScale: motion ? 1.12 : 1.0,
    motionOpacity: motion ? 0.9 : 1.0,
    // Status
    statusLabel: deriveStatusLabel(forgeState),
    statusEmoji: deriveStatusEmoji(forgeState),
    // Connection
    isConnected: forgeState?.is_connected ?? false,
  };
}

/**
 * PresentationAdapter — React component that applies mapPresentation
 * and renders nothing itself (it is a mapper, not a renderer).
 *
 * Consumers call mapPresentation() and use the result to drive their own
 * rendering. This component exists as a convenience wrapper for the common
 * case and to document the interface.
 */
export default function PresentationAdapter({ forgeState, mode = 'orb', modelUrl = null, children }) {
  const presentation = mapPresentation(forgeState, { mode, modelUrl });
  return children ? children(presentation) : null;
}
