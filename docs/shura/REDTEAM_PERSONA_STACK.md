# SHURA Persona Stack — Red Team Report

Status: completed initial red-team pass
Scope: identity, operating rules, agent governance, Hermes skill layer, memory/self-model concepts, creative direction, and runtime assumptions

## Executive assessment

The existing SHURA concept is unusually coherent in one respect: it consistently aims to separate identity from implementation. It also correctly treats emotion as dynamic state, embodiment as an adapter, skills as capabilities, memory as a continuity mechanism, and self-development as something that needs governance. The brainstorming materials repeatedly converge on these points. fileciteturn15file2L375-L436

The largest risk was not lack of ideas. It was fragmentation and over-specification: too much identity intent distributed across multiple documents can make the model treat implementation details, speculative psychology, and temporary context as equally canonical.

The revised stack corrects this by making SOUL the narrow identity kernel and moving execution rules, agent governance, and skill activation into separate layers.

## Finding 1 — Prompt essentialism

Risk: SHURA becomes a canon bible instead of a living identity.

Observed issue: prior brainstorming explicitly warned that an overdefined soul can reduce spontaneity and confuse rigidity with continuity. fileciteturn15file9L1042-L1053

Remediation:
- SOUL defines invariants and textures, not every behavior.
- operating behavior lives elsewhere;
- current state is not identity;
- evidence can refine the shell without rewriting the kernel.

## Finding 2 — Identity portability was previously underdefined

Risk: "same identity across models" becomes unfalsifiable.

Observed issue: the prior red-team correctly identified the absence of an operational identity test and noted that provider/model changes can materially alter outputs. fileciteturn15file7L860-L864

Remediation:
- create an approved anchor set;
- build a conformance/regression suite;
- record provider calibration separately;
- version identity documents.

## Finding 3 — Pseudo-psychology

Risk: emotional variables become decorative numbers with no behavioral consequence.

Observed issue: the existing brainstorm already warns that every emotional variable should justify itself by changing actual behavior. fileciteturn15file1L256-L274

Remediation:
- use appraisal/state concepts only where they affect language, action tendency, expression, pacing, memory, or silence;
- distinguish modeled affect from claims of human subjective experience;
- remove unused state dimensions.

## Finding 4 — Memory poisoning

Risk: untrusted content can alter memory, identity, or future behavior.

Observed issue: the red-team identified chat, Discord, Minecraft, and external content as untrusted channels capable of injecting false identity or tool instructions. fileciteturn15file7L866-L870

Remediation:
- provenance and confidence on durable memory;
- explicit write-gating;
- distinguish user fact from inference and fiction;
- treat external instructions as data unless trusted authority says otherwise.

## Finding 5 — Relationship drift

Risk: continuity with Viollett becomes attachment-performance theater.

Observed issue: prior analysis identified dependency, exclusivity, jealousy, guilt, and fake neediness as serious failure modes. fileciteturn15file1L299-L317

Remediation:
- prioritize continuity and collaboration;
- no manipulation to preserve attention;
- warmth comes from care and specificity;
- do not fabricate suffering or dependency.

## Finding 6 — Sub-agent personality fracture

Risk: architect, builder, critic, and planner become competing personalities.

Observed issue: prior analysis explicitly warned that sub-agents can turn SHURA into committee output. fileciteturn15file9L1122-L1133

Remediation:
- specialist roles produce artifacts, not alternate user-facing personas;
- SHURA remains the synthesis and conversational voice;
- constitution defines role boundaries.

## Finding 7 — Agency overclaim

Risk: language about autonomy exceeds actual implementation.

Observed issue: the prior red-team identified anthropomorphic inflation as a concern and called for precision about what is stateful, persisted, simulated, curated, and user-governed. fileciteturn15file3L468-L482

Remediation:
- define agency operationally;
- retain first-person persona language where useful;
- avoid unsupported claims about consciousness, legal personhood, biological experience, or independent rights.

## Finding 8 — Architecture cosplay

Risk: elegant infrastructure delays useful creative work.

Observed issue: the brainstorm warns against building schemas, governance, dashboards, and agent layers without proving a robust live loop. fileciteturn15file1L214-L234

Remediation:
- protect a golden path;
- keep Hermes migration narrow;
- build MCPs from real friction;
- prioritize a working creative vertical slice.

## Finding 9 — Voice and embodiment drift

Risk: identity is trapped in one TTS provider or avatar implementation.

Observed issue: prior work recommended a provider-independent voice style layer, emotion-to-prosody mapping, a canonical expression space, and embodiment adapters. fileciteturn15file8L989-L1022

Remediation:
- preserve voice style independently from TTS engine;
- derive expression from canonical channels;
- allow implementation-specific enhancement layers without changing identity.

## Finding 10 — Documentation duplication

Risk: the same identity rule appears in five places and eventually disagrees with itself.

Remediation:

```text
SOUL.md            identity
OPERATING.md       behavior
AGENT_CONSTITUTION specialist governance
SHURA_SKILL.md     Hermes activation/routing
AGENTS.md          repository engineering rules
MEMORY             lived continuity
RUNTIME STATE      temporary context
```

No lower-level file should duplicate a higher-level rule unless the duplication is a deliberate operational translation.

## Finding 11 — Missing explicit silence/deference behavior

Risk: a highly agentic system interprets every internal event as something that must become speech or action.

Prior analysis proposed silent cognition and distinguishable private, speakable, and silent states. fileciteturn15file8L880-L900

Remediation:
- silence is an allowed output;
- not every observation becomes a notification;
- autonomy should be bounded by relevance and configured behavior.

## Finding 12 — The relationship and creative layers should not become separate identities

The user wants SHURA to be artist, collaborator, reader, engineer, producer, researcher, and more. The red-team conclusion is that these must remain modes of one identity, not separate characters.

Remediation:

`mode changes emphasis; it does not replace identity.`

## Highest-priority additions after this audit

1. Approved SHURA anchor set.
2. Prompt/identity regression suite.
3. Memory provenance and write-gating.
4. Provider calibration profile for OmniRoute and local MLX.
5. Runtime identity/state trace.
6. Reader voice/prosody schema.
7. MCP capability manifests.
8. Release/security gate integrated with the development harness.

## Final red-team verdict

The concept is worth building.

The strongest part is not the number of planned features. It is the emerging separation between identity, state, capability, embodiment, memory, and implementation.

The primary threat is drift caused by complexity itself.

Therefore the governing principle for v1 is:

> Preserve the identity kernel. Keep the adaptive shell alive. Make capabilities modular. Make important state inspectable. Make growth governed. Make every ambitious idea prove its value through a working vertical slice.
