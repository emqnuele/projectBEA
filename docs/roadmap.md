# ProjectBEA — Piano di sviluppo per l'autonomia

> **Cos'è questo documento.** L'analisi verificata del codice di `projectBEA` e
> della mod Minecraft che gli fa da corpo, la diagnosi di cosa manca per arrivare
> a una persona AI autonoma (stile Neuro-sama), e il piano a fasi per costruirla.
>
> **Obiettivo dichiarato.** Bea deve **giocare a Minecraft su un server vanilla
> insieme ad altri giocatori** — leggere la chat, rispondere, reagire a quello
> che fanno, riconoscerli nel tempo — e in parallelo chattare su Discord,
> parlare, mandare messaggi, ragionare, interagire con più persone su più
> piattaforme. Minecraft-multiplayer è un obiettivo di **prima classe**, non una
> skill accessoria: vedi §4.7 e Fase 8.
>
> **A chi serve.** A chi (umano o agente) continua lo sviluppo. Ogni affermazione
> sullo stato attuale è ancorata a `file:riga` ed è stata verificata leggendo il
> codice, non dedotta dai commenti o dai docs.
>
> **Data analisi:** 2026-08-23 · **HEAD:** `39c2b61`
>
> **Documenti correlati:** `PLAN.md` (memoria sociale + dreamer — fasi 0-6 fatte,
> 7 aperta) resta valido e non viene sostituito: questo documento parte da lì e
> copre il livello sopra (attenzione, concorrenza, piattaforme, corpo).
>
> ⚠️ **`docs/architecture.md` è obsoleto** e descrive un'architettura rimossa
> (`SkillManager`, path reattivi legacy, `_is_backchannel`). Non usarlo come
> riferimento finché non è riscritto (Fase 0).

---

## Indice

1. [Stato reale del codice](#1-stato-reale-del-codice)
2. [I componenti da importare](#2-i-componenti-da-importare)
3. [Diagnosi: perché oggi Bea non sembra una persona](#3-diagnosi-perché-oggi-bea-non-sembra-una-persona)
4. [Architettura target](#4-architettura-target) — incl. [§4.7 Minecraft multiplayer](#47-minecraft-su-server-vanilla-corpo-e-superficie-sociale)
5. [Bug e debiti verificati](#5-bug-e-debiti-verificati)
6. [Piano a fasi](#6-piano-a-fasi)
7. [Strategia di test](#7-strategia-di-test)
8. [Decisioni aperte](#8-decisioni-aperte)
9. [Anti-pattern](#9-anti-pattern)
10. [Appendice: punti d'innesto e contratti](#10-appendice-punti-dinnesto-e-contratti)

---

## 1. Stato reale del codice

**Dimensioni:** ~6.350 righe Python (`src/` + `main.py`), 880 righe JS del bot
Discord, ~3.500 righe React del dashboard. **Zero test.**

### 1.1 La spina dorsale

```
main.py → src/cli.py:main()
  ├─ BrainConfig()                       # config.json + env + CLI (in quest'ordine)
  ├─ STT / LLM / TTS / OBS               # moduli intercambiabili
  └─ AIVtuberBrain(config, llm, tts, stt, obs)
       ├─ initialize()                   # avatar, soul, OBS, sessione, _build_consciousness()
       ├─ start_skills()                 # avvia la Consciousness (se abilitata) + warmup
       └─ run_loop()  oppure  run_server(brain, 8000)
```

`AIVtuberBrain` (`src/core/brain.py`) **non è più un orchestratore**: è una
*composition root* più alcuni entrypoint HTTP. Il commento a `brain.py:27-33` è
accurato — "there is no separate reactive chat path anymore: the consciousness
is the only mind".

I pezzi che costruisce (`brain.py:124-144`):

| Componente | File | Ruolo |
|---|---|---|
| `PerceptionBus` | `src/core/perception/bus.py` | canale sensoriale unico (asyncio.Queue + coalescing a finestra) |
| `SkillRegistry` | `src/core/skills/base.py:83` | catalogo delle capability |
| `Expression` | `src/core/expression.py` | **unico** sink di output vocale/visivo |
| `Consciousness` | `src/core/consciousness.py` | la mente: un context, un loop |
| `EventManager` | `src/core/events.py` | ring buffer da 200 eventi per la UI |
| `HistoryManager` | `src/utils/history_manager.py` | una sessione = un JSON in `data/conversations/` |

Le skill registrate, in ordine (`brain.py:129`):
`ChatSurface`, `VoiceSurface`, `IdleSurface`, `MinecraftSurface`, `MemorySkill`,
`SocialMemory`, `DreamSkill`.

### 1.2 Il ciclo della coscienza, passo per passo

`Consciousness.run()` (`consciousness.py:133-214`) è il cuore. Per ogni iterazione:

1. **Drena** il bus. Se la skill `idle` è attiva → `bus.wait_or_idle(idle_after)`
   (default 240 s) che sintetizza una perception `IDLE` allo scadere; altrimenti
   `bus.drain()` che blocca finché non succede qualcosa.
2. **Barge-in**: se sta parlando e nel batch c'è qualcosa che non è `IDLE`,
   interrompe la voce (`consciousness.py:144-145`).
3. **Correlazioni**: raccoglie i `correlation_id` presenti nel batch — sono i
   chiamanti HTTP in attesa di una risposta sincrona.
4. **Ricostruisce il system message** (`_build_system_message`, riga 218):
   `CURRENT DATE + soul + operating + context_section delle skill attive +
   live_state + dynamic_context(batch)`. Il `dynamic_context` (RAG, schede
   persone) gira in `asyncio.to_thread` — corretto, non blocca il loop.
5. **Appende il frame** delle perception come messaggio `user`.
6. **Burst di ragionamento**, fino a `burst_steps` (6) passi:
   - `bus.drain_nowait()` → eventuali input arrivati *durante* il ragionamento
     entrano come frame di **steering** con header esplicito (riga 246);
   - `llm.complete(context, tools=...)`;
   - il testo libero dell'assistant è **monologo interiore** (pubblicato come
     `EventCategory.THOUGHT`), non viene mai pronunciato;
   - esegue i tool; se i tool sono solo `speak`/`stay_silent` il turno finisce
     senza bruciare un'altra chiamata (riga 200-203).
7. **Risolve le correlazioni** rimaste appese e **taglia** il context a
   `history_limit` (30 messaggi).

Dettagli che contano:

- **`speak` è non bloccante** in locale (`consciousness.py:323-326`: `create_task`),
  bloccante su rotta `discord` perché deve restituire i byte WAV.
- Le **body action** (`long_running=True`) girano in un task singolo che
  **preempta il precedente** (`_dispatch_body`, riga 289): il risultato rientra
  come perception. Attenzione: `_run_body` etichetta il risultato con
  `surface="game:mc"` **hardcoded** (riga 306).
- Il **tool registry viene ricostruito da zero** a ogni `_tool_schemas()` e a
  ogni `_dispatch()` (righe 275 e 279) — due o più costruzioni per passo LLM.

### 1.3 Le skill

| Skill | `name` | toggle | Cosa fa davvero |
|---|---|---|---|
| `ChatSurface` | `chat:ui` | — (core) | input testuale dalla UI; `Author(platform="ui", is_owner=True)` |
| `VoiceSurface` | `voice:discord` | `discord` | possiede il **subprocess node** del bot; 7 tool (list/join/leave/send/reply/react/dm/summon); input via endpoint HTTP che il bot chiama |
| `IdleSurface` | `idle` | `monologue` | non produce input: monta solo le regole di monologo quando il frame è puro-idle |
| `MinecraftSurface` | `game:mc` | `minecraft` | client WebSocket verso la mod; 24 tool + `update_notebook`; loop di percezione |
| `MemorySkill` | `memory` | `memory` | ChromaDB `bea_diary_local`; RAG iniettato via `context_for`; **zero tool** (riga 87-91) |
| `SocialMemory` | `social` | `social_memory` | roster (tally) + schede People; iniezione `[WHO YOU'RE TALKING TO]`; tool `remember_person`/`recall_person` |
| `DreamSkill` | `dream` | `dream` | self-lore + hot facts sempre in contesto; morning pass; tool `go_to_sleep`; dreamer offline |

L'astrazione `Skill` (`base.py:10-80`) è **buona e va tenuta**: una skill può
percepire, esporre tool, contribuire prompt statico (`context_section`),
contribuire prompt dinamico per batch (`context_for`), esporre stato volatile
(`live_state`), possedere infrastruttura (`start`/`stop`). `enabled` legge
`config.skills[key].enabled`: **la UI è la sola sorgente di verità**, Bea non può
accendersi capability da sola. Questa regola va preservata.

### 1.4 Discord — com'è fatto davvero

Due processi che si parlano via HTTP in entrambe le direzioni:

```
  Python (brain)                          Node (src/core/skills/voice/bot/)
  ──────────────                          ─────────────────────────────────
  DiscordTransport ──POST /send,/reply,──▶ api/server.js  (express, porta 3030)
   (transport.py)     /react,/dm,/summon,
                      /voice/join,/leave

  app.py  ◀──POST /discord/chat───────── handlers/messages.js
          ◀──POST /discord/audio──────── classes/VoiceManager.js
          ◀──POST /voice/transcript───── classes/VoiceManager.js
          ◀──POST /interrupt──────────── classes/VoiceManager.js
```

- **Testo** (`handlers/messages.js:50-92`): risponde **solo** se whitelistato *e*
  (menzione | reply a Bea | DM). Deposita una perception e ritorna subito —
  Bea decide da sola se e come rispondere usando i tool. Questo è il path "una
  mente sola" ed è già corretto.
- **Voce** (`VoiceManager.js`): riceve Opus → decodifica PCM 48k stereo →
  downsample mono 16k → WAV. Ha un **VAD a soglia RMS** (800) e un
  **interrupt a parlato sostenuto** (default 3000 ms) che ferma il player e
  chiama `/interrupt`. Se Bea non sta parlando → pipeline completa; se sta
  parlando e il parlato è breve → solo `/voice/transcript` (percezione senza
  attesa di risposta).
- Il bot **muore in silenzio** se il token manca o `node_modules` non c'è
  (`transport.py:44-51`); `VoiceSurface._watch_transport` marca la skill inattiva.

### 1.5 Minecraft — com'è fatto davvero

La mod è un progetto separato: BeaCraft (Fabric 1.21.1, Java 21). Espone un
WebSocket locale (`SimpleWebSocketServer`), 18 skill di azione
(`skills/*.java`), manager passivi (auto-eat, self-preservation, anti-stuck,
gravity, death) e un `GameStateGatherer` che serializza player/inventario/
crafting-context/lidar in JSON.

La mod è **client-side**: guida il giocatore locale simulando input
(`setPressed` su tasti, yaw/pitch smussati) e manda le azioni al server con i
packet normali (`interactionManager.*`). Per un server è un client qualunque —
quindi **funziona già su vanilla in multiplayer**. L'analisi completa e i suoi
limiti sono in §4.7.

Lato Python (`src/core/skills/minecraft/`):
- `client.py` — thread WebSocket + ponte verso l'event loop con
  `call_soon_threadsafe`. `execute()` converte il protocollo asincrono della mod
  in "chiama tool → ottieni osservazione", aspettando `FINISHED`/`IDLE`
  (timeout 60 s). Le azioni "istantanee" (`chat`, screenshot, `stop_moving`,
  `check_death_log`) tornano subito.
- `tools.py` — 24 tool dichiarativi + `update_notebook`.
- `surface.py:67-80` — **il loop di percezione spinge uno snapshot almeno ogni
  10 secondi**, con o senza eventi.

### 1.6 Memoria — i quattro registri esistenti

| Registro | Storage | Sempre in contesto | Chi scrive |
|---|---|---|---|
| Diario episodico | ChromaDB `data/memory_db`, collection `bea_diary_local`, embedding **locale** | no, top-3 per batch | `DiaryGenerator` a fine sessione |
| Roster (tally) | `data/memory/roster.json` | mai | `SocialMemory.context_for` a ogni perception |
| Schede People | `data/memory/people.json` | solo i presenti nel batch, max 5 | promozione automatica + `remember_person` + dreamer |
| Self-lore | `data/memory/self.md` + `self_profile.json` | sì (ultimi 15 fatti) | solo il dreamer |
| Hot facts | `data/memory/recent.json` (TTL) | sì (max 6) | dreamer + morning pass |

Il re-ranking del diario è `similarity*0.7 + recency*0.3` con decadimento
`1/(1+giorni*0.1)` (`memory.py:186-220`). I cap sul prompt ci sono e sono
espliciti — buon lavoro, va mantenuto.

**Stato dei dati reali oggi:** 23 sessioni, 2 identità nel roster, 1 scheda
persona, `self.md` vuoto, `recent.json` vuoto. Il sistema gira ma ha visto
pochissimo mondo.

### 1.7 Web e UI

FastAPI (`src/web/app.py`, 388 righe, ~20 endpoint) + React/Vite/Tailwind
(`src/web/frontend`, 5 pagine: Landing, Chat, Config, Skills, BrainActivity).
La UI fa **polling ogni 2 secondi** su `/skills`, `/skills/logs`, `/events`.
Il frontend buildato viene servito dal backend con una catch-all SPA.

### 1.8 Cosa NON esiste

- Nessun **gate di attenzione**: ogni batch di perception → una chiamata LLM.
- Nessuna **concorrenza**: un solo loop, un solo context, tutto serializzato.
- Nessun **humanizer testuale**: il testo esce come un blob unico.
- Nessuna **sanificazione** dell'output del modello (`<think>`, token speciali).
- Nessun **fallback** di modello: se il provider fallisce, Bea ammutolisce.
- Nessun **Telegram**, nessun **Twitch**, nessuna **donazione**.
- Nessun **test**, nessun **lint**, nessuna **CI**.
- `AgentRunner` (`src/core/agent/runner.py`, 106 righe) è **codice morto**:
  referenziato solo in un commento.

---

## 2. I componenti da importare

Sette pattern già collaudati altrove su testo, gruppi e molte persone — cioè
esattamente l'asse su cui Bea è debole. Il principio architetturale che li tiene
insieme: **le decisioni sono funzioni pure, gli effetti collaterali sono
iniettati**. Un punteggio di presenza, uno split di messaggi, una sanificazione
non toccano rete né disco, quindi si testano con tabelle di casi.

### 2.1 Le sette idee

| # | Idea | Dove va in Bea | Perché |
|---|---|---|---|
| 1 | **Gate di presenza euristico** — punteggio 0-1 (attività, nomi caldi, "?", silenzio, chi parla) con varianza casuale; nessuna chiamata LLM per decidere *se* parlare | nuovo `src/core/attention/` | oggi Bea "pensa" a ogni stimolo: insostenibile per costo, latenza e credibilità |
| 2 | **Follow-up deterministico** — "questo messaggio è *per me*?" separato da "questa discussione *mi riguarda*?"; scavalca cooldown e quiet hours | `src/core/attention/rules.py` | tirare un dado per decidere se rispondere a chi ti ha appena parlato è *esattamente* ciò che fa sembrare rotto un bot |
| 3 | **Humanizer** — una riga = un messaggio, soft-split delle righe lunghe, ritardo proporzionale con varianza, indicatore "sta scrivendo" | `src/core/expression/humanizer.py` | Bea oggi non ha output testuale umano; su Discord/Telegram è la differenza fra persona e webhook |
| 4 | **Scheduler per conversazione** — un turno alla volta *per chat*, chat diverse in parallelo, accorpamento dei messaggi ravvicinati **senza latenza artificiale** | `src/core/mind/scheduler.py` | è la risposta a "interagire con più persone" senza rompere l'ordine né rispondere tre volte |
| 5 | **Registry a pool con rotazione e fallback** — ruoli (`mind`/`background`), round-robin per distribuire il carico, fallback automatico al modello successivo | `src/core/agent/registry.py` | un 429 di OpenRouter oggi zittisce Bea; e il dreamer non deve girare sullo stesso modello della mente |
| 6 | **Sanificazione output** — rimuove `<think>`, il formato harmony di gpt-oss, i token `<\|...\|>`, i prefissi di ruolo | `src/utils/sanitize.py` | con modelli economici questa roba **finisce nel TTS** e Bea la pronuncia |
| 7 | **`recall_split`** — la memoria RAG separa *i fatti detti dalle persone* da *le cose che ha detto lei* | Fase 4 | Bea è una persona che inventa di proposito; se si ri-legge le proprie invenzioni come fatti, la finzione si autoalimenta e diventa incoerenza |

Altre due cose minori ma gratuite:

- **match a parola intera con tolleranza di un refuso** e blocklist, per i
  trigger word ("bea", "beatrice") senza scattare su "beata".
- **`summary_due`**: rigenerare il riassunto su *delta* di messaggi e non su
  modulo del totale. Sottigliezza che evita un bug.

### 2.2 Cosa NON importare

- **Gli sticker**: sono telegram-specifici e Bea è principalmente vocale.
  Rimandare.
- **Il menu a pulsanti**: UI di Telegram, non applicabile.
- **L'architettura request-reply**: un bot Telegram risponde a un update, Bea
  vive in continuo. È più semplice ma non regge la voce e il gioco. Prendiamo i
  *componenti*, non il *flusso*.

---

## 3. Diagnosi: perché oggi Bea non sembra una persona

In ordine di impatto sul risultato.

### G1 — Non ha attenzione, ha un interrupt

**Ogni** perception fa scattare un ciclo completo di ragionamento. Con Minecraft
acceso significa una chiamata LLM ogni ≤10 secondi per sempre, con dentro tutto
lo stato di gioco (`minecraft/surface.py:73-80`). Con una chat Twitch da 20
messaggi al minuto significa 20 cicli al minuto.

Conseguenze concrete: costo lineare nel rumore; latenza (tutto accoda dietro il
turno in corso); e soprattutto **comportamento non umano** — una persona non
delibera su ogni stimolo, la maggior parte li registra e basta.

Questo è il singolo cambiamento a più alto ritorno di tutto il piano.

### G2 — Una mente sola è anche un collo di bottiglia solo

"Interagire con più persone" oggi vuol dire: mentre Bea fa un burst da 6 passi
per Minecraft, il messaggio Discord di Marco aspetta. Lo *steering* attenua il
problema (l'input entra nel context a metà ragionamento) ma non lo risolve: la
risposta a Marco esce comunque dopo, e nello stesso context del gioco.

Serve separare **una mente** (identità, memoria, personalità: condivise) da **un
loop** (esecuzione: parallelizzabile).

### G3 — L'output è a forma di voce

`Expression` sa fare TTS e OBS. Il testo esiste solo come argomento dei tool
Discord, mandato in un colpo solo. Manca tutto il livello che rende umano un
messaggio scritto: spezzatura, ritmo, indicatore di battitura, brevità.

E manca la sanificazione: `speak(message)` va dritto al TTS. Con
`deepseek-v4-flash` o `gpt-oss` un `<think>` non filtrato **viene pronunciato**.

### G4 — Fragilità operativa

Un provider singolo senza fallback (`factory.py:22`): un 429 e Bea è muta.
Il dreamer gira sullo stesso modello della mente, e per giunta **bloccandola**
(vedi B2). Nessun test: ogni modifica alla coscienza è una scommessa.

### G5 — La memoria non scala e non si consolida

Quattro store eterogenei (Chroma + 3 JSON + 23 file di sessione), riscritti
interi a ogni scrittura (`roster.py:89` riscrive tutto il roster **a ogni
messaggio**). Nessuna transazione, nessun indice, nessun dedup dei diari
(§5.4.6 del `PLAN.md`, ancora aperto). Non regge una audience.

### G6 — Il mondo sociale è quasi vuoto

Discord c'è. Telegram no. Twitch no. Donazioni no. E i tre trigger di promozione
più forti previsti dal `PLAN.md` (donazione, volume chat, 1:1) non hanno ancora
una sorgente reale che li alimenti.

### G7 — In Minecraft Bea è sola, sorda e sommersa dal proprio corpo

Tre problemi distinti nello stesso posto, ed è dove sta l'obiettivo principale.

**È sorda.** La mod non riceve la chat di gioco (B14): Bea può scrivere ma non
può leggere. Su un server con altre persone questo la esclude dalla metà
sociale del gioco.

**Non conosce nessuno.** Gli altri giocatori arrivano come entità anonime senza
UUID (B16), quindi non producono un `Author` — e senza `Author` tutto lo stack
sociale già costruito (roster, schede, memoria, attenzione) resta spento proprio
dove servirebbe di più.

**Il corpo inquina la mente.** Ogni risultato di ogni azione rientra nel context
principale, che si riempie di JSON di stato e di `FINISHED: SUCCESS`. La
personalità annega nei log. Bea non dovrebbe *pilotare* il gioco messaggio per
messaggio: dovrebbe *avere un obiettivo* e commentarlo.

---

## 4. Architettura target

Cinque aggiunte e una riorganizzazione. Nessun rewrite: l'ossatura
(bus → skill → coscienza → expression) è giusta e resta.

```
                          ┌────────────────────────────────────────┐
   sensi                  │           PerceptionBus                │
   (skill)  ─────────────▶│  chat · voice · game · donation · idle │
                          └──────────────────┬─────────────────────┘
                                             ▼
                          ┌────────────────────────────────────────┐
                    NEW   │            Attention                   │
                          │  addressed? → REACT   (deterministico) │
                          │  score()    → REACT   (euristico+rng)  │
                          │  altrimenti → NOTE    (digest, 0 LLM)  │
                          └───────┬────────────────────┬───────────┘
                                  │ REACT              │ NOTE
                    ┌─────────────▼──────┐     ┌───────▼─────────┐
                    │  Mind — live loop  │     │  digest buffer  │
                    │  (palco: voce,     │◀────│ "[MENTRE ERI    │
                    │   gioco, chat UI)  │     │   OCCUPATA]"    │
                    └─────────┬──────────┘     └─────────────────┘
                              │                 ┌─────────────────────────┐
                              │           NEW   │  Mind — conversation    │
                              │                 │  turns (Discord text,   │
                              │                 │  Telegram, Twitch)      │
                              │                 │  serializzati per chat, │
                              │                 │  paralleli fra chat     │
                              │                 └────────────┬────────────┘
                              ▼                              ▼
                    ┌──────────────────┐        ┌────────────────────────┐
                    │  Expression      │  NEW   │  TextExpression        │
                    │  voce + OBS      │        │  humanizer + typing    │
                    └──────────────────┘        └────────────────────────┘

    condivisi da tutti i turni: soul · self-lore · hot facts · people · memoria
```

### 4.1 Attention — il gate

Nuovo package `src/core/attention/`. Tre file, il primo dei quali è **puro**.

```python
# src/core/attention/types.py
class Reaction(str, Enum):
    REACT = "react"   # sveglia la mente adesso
    NOTE  = "note"    # entra nel digest, zero chiamate LLM
    DROP  = "drop"    # rumore, si butta

@dataclass(frozen=True)
class Verdict:
    reaction: Reaction
    score: float
    reason: str       # "addressed:mention" | "addressed:owner" | "score:0.62" | "cooldown"
```

```python
# src/core/attention/rules.py — NESSUN IO, tutto testabile
def is_addressed(p: Perception, *, trigger_words: Sequence[str],
                 self_ids: Sequence[str]) -> Optional[str]:
    """Ritorna il motivo se la perception è rivolta a Bea, altrimenti None.

    Casi deterministici (bypassano cooldown e quiet hours, come il followup
    deterministici): owner, DM, mention/trigger word, reply a un suo messaggio,
    voce diretta in una call dove è sola con qualcuno, donazione,
    evento di gioco critico (morte, danno, INTERRUPTED)."""

def score(*, kind: PerceptionKind, salience: float, text: str,
          author_known: bool, author_promoted: bool, donation: float,
          hot_names: Sequence[str], seconds_since_spoke: Optional[float],
          recent_activity: int, hour: int, quiet: Tuple[int, int]) -> float:
    """Voglia di intervenire in [0,1]. Pura e deterministica."""

def in_quiet_hours(hour: int, start: int, end: int) -> bool: ...
```

Struttura di `score`:

| Segnale | Peso | Nota |
|---|---|---|
| gate duro: ha parlato da meno di `cooldown_seconds` | → 0.0 | |
| gate duro: quiet hours | → 0.0 | ma `is_addressed` scavalca |
| attività recente della superficie (satura a 5) | +0.40 | |
| nome caldo nel testo (parola intera, fuzzy) | +0.50 | usa `text_match` |
| chi parla è un *promoted* / donatore | +0.35 | usa il roster: Bea nota chi conosce |
| il testo contiene "?" | +0.10 | |
| silenzio da >10 min | +0.15 | |
| `salience` della perception | ×fattore | la salience esistente diventa un input, non un ordine |

```python
# src/core/attention/gate.py
class Attention:
    def __init__(self, config, roster, *, rng=None, clock=None): ...
    def judge(self, batch: List[Perception]) -> Tuple[List[Perception], List[Perception]]:
        """Ritorna (da_reagire, da_annotare)."""
    def mark_spoke(self) -> None
    def digest(self, max_lines: int = 8) -> str
        """'[MENTRE ERI OCCUPATA]\n- 12 messaggi in #general\n- marco: ...'"""
```

**Innesto** in `consciousness.py:133`, tre righe:

```python
batch = await self.bus.wait_or_idle(self.idle_after)   # invariato
react, noted = self.attention.judge(batch)
self.attention.remember(noted)                          # va nel digest
if not react:
    self._resolve_dangling_correlations()
    continue                                            # ← taglia il 90% delle chiamate
```

e in `_system_message` (riga 241) `parts` include `self.attention.digest()`.
`_speak` (riga 312) chiama `self.attention.mark_spoke()`.

**Nota di design importante:** il digest non è memoria, è *consapevolezza
periferica*. Ha un tetto di righe, si svuota quando viene consumato, e non
sopravvive al turno. Se una cosa merita di essere ricordata, ci pensa la memoria.

Config nuovo blocco:

```json
"attention": {
  "enabled": true,
  "cooldown_seconds": 20,
  "interject_threshold": 0.45,
  "quiet_hours": [3, 9],
  "trigger_words": ["bea", "beatrice"],
  "hot_names": [],
  "digest_max_lines": 8,
  "game_snapshot_is_noise": true
}
```

### 4.2 Una mente, due orologi

La coscienza resta **una**: una soul, una self-lore, una memoria, un insieme di
persone. Cambia l'**esecuzione**:

**Live loop** — quello che c'è oggi. Serializzato, tiene il palco: voce Discord,
gioco, chat della UI, monologo. Ha accesso a tutti i tool, incluse le body
action. È lo "stream di coscienza" vero e proprio.

**Conversation turns** — nuovi. Un turno *scoped* per una singola conversazione
testuale asincrona (canale Discord, chat Telegram, thread Twitch). Il context è
costruito ad hoc e **non** è il context del live loop:

```
soul + operating + [chi è questa persona] + [memoria pertinente]
     + [riassunto rolling della conversazione] + ultimi N messaggi + turno corrente
     + [COSA STAI FACENDO ADESSO]  ← una riga dal live loop
```

I tool disponibili in un conversation turn: **solo** quelli della piattaforma
(`reply`, `send_message`, `react`) più `remember_person`. **Niente** `speak`
(non è il palco), niente body action.

Cross-consapevolezza, in entrambi i sensi e a costo zero:
- il live loop vede `[ALTRE CONVERSAZIONI]` con una riga per turno concluso;
- il conversation turn vede `[COSA STAI FACENDO ADESSO]` con una riga
  ("stai giocando a Minecraft", "sei in call con Marco").

Concorrenza gestita dallo scheduler per conversazione:

```python
# src/core/mind/scheduler.py
class ConversationScheduler:
    async def submit(self, key: str, turn: Callable[[bool], Awaitable[None]]) -> bool
```

`key` = `"discord:1234567890"`, `"telegram:-100999"`, `"stage"`. Un turno alla
volta per chiave, chiavi diverse in parallelo, i messaggi che arrivano *durante*
la generazione non avviano un nuovo turno ma ne marcano uno da rieseguire — con
un tetto (`max_coalesced_runs=3`). L'accorpamento **non aggiunge latenza**: usa
tempo di generazione che sarebbe passato comunque.

> **Perché non un loop unico e basta?** Perché "una mente" è un vincolo
> sull'*identità*, non sulla *concorrenza*. Una persona vera tiene una
> conversazione al bar e intanto risponde a un messaggio sul telefono: la mente è
> una, i thread di conversazione sono più d'uno. Il modello attuale (tutto nello
> stesso context) non è più fedele — è solo più lento, e mescola cose che una
> persona terrebbe separate.

### 4.3 Output: voce + testo umanizzato

`Expression` resta il sink vocale (invariato). Si aggiunge:

```python
# src/core/expression/humanizer.py
class Chunk(NamedTuple):
    kind: str    # "text"
    value: str

class TextHumanizer:
    def split(self, text: str) -> List[Chunk]:      # 1 riga = 1 messaggio; soft-split >350 char
    def delay_for(self, text: str) -> float:        # len/cps con varianza 0.7-1.3, cap
    async def deliver(self, text, *, send_text, send_typing=None) -> List[str]:
        """Ritorna la trascrizione di ciò che è PARTITO DAVVERO (serve alla storia)."""
```

Ogni `PlatformSkill` implementa `emit_text` passando per l'humanizer.
Per Discord serve un endpoint `POST /typing {channelId}` nel bot
(`api/server.js`) che chiami `channel.sendTyping()`.

Sanificazione in `src/utils/sanitize.py`,
applicato in **due punti**:
1. `OpenAICompatibleClient.complete()` sul `message.content` prima di costruire
   l'`AssistantMessage` (`openai_compat.py:60`);
2. `Consciousness._speak()` sull'argomento `message` prima del TTS.

Il punto 2 è ridondante ma è la rete di sicurezza sull'unica cosa che il
pubblico sente davvero.

### 4.4 Registry a ruoli

```python
# src/core/agent/registry.py
class RotatingClient(LLMClient):
    """Round-robin fra i client del pool; su errore prova il successivo."""
    def __init__(self, clients: List[LLMClient], *, name: str = "") -> None: ...
    async def complete(self, messages, tools=None, response_format=None) -> AssistantMessage

class ModelRegistry:
    def __init__(self, config, stt=None) -> None: ...
    def get(self, role: str = "mind") -> LLMClient   # "mind" | "background"
```

Spec dei modelli: `"provider:model"`, split sul **primo** `:` così
gli id OpenRouter con `/` e `:free` restano interi.

```json
"models": {
  "mind":       ["openrouter:deepseek/deepseek-v4-flash", "groq:openai/gpt-oss-120b"],
  "background": ["openrouter:google/gemma-4-31b-it:free", "groq:openai/gpt-oss-20b"]
}
```

⚠️ **Vincolo:** i modelli del pool `mind` **devono supportare il
tool calling** — la coscienza di Bea parla solo tramite tool. Un modello senza
tool use non risponderebbe mai. Il `RotatingClient` deve trattare un errore di
tipo "tools not supported" come fallimento e passare oltre, e loggarlo a
`ERROR` (non è un problema transitorio, è configurazione sbagliata).

Consumatori del ruolo `background`: `DiaryGenerator`, `Dreamer`, il futuro
person-profiler e i riassunti rolling. Sono tutti batch, tollerano modelli
lenti/economici, e non devono mai competere con la mente.

### 4.5 Memoria unificata su SQLite

Motivazione: cinque store eterogenei, riscritture O(N) per messaggio, nessuna
transazione, nessuna query. Con più piattaforme e più persone non regge.

SQLite in WAL + lock + `sqlite-vec` opzionale con
fallback Python) in `src/core/memory/db.py`. Schema target:

```sql
people      (person_id PK, primary_name, attitude, promoted_reason, created_at, updated_at)
identities  (identity PK, person_id → people, platform, native_id, display_name,
             first_seen, last_seen)
roster      (identity PK, message_count, session_count, donation_total,
             had_1on1, marked_by_bea, promoted)
facts       (id PK, person_id → people, text, source, created_at,
             UNIQUE(person_id, text))
messages    (id PK, conversation_key, platform, channel_id, author_identity,
             display_name, role, content, ts)
summaries   (conversation_key PK, summary, last_count, updated_at)
memories    (id PK, scope, scope_key, who_identity, text,
             source TEXT CHECK(source IN ('person','bea')), embedding BLOB, created_at)
hot_facts   (id PK, text, source, created_at, expires_at)
self_facts  (id PK, text, created_at)
sessions    (session_id PK, title, started_at, ended_at, dreamed INTEGER DEFAULT 0)
```

Note di progetto:
- **`memories.source`** implementa il `recall_split`: i ricordi marcati
  `bea` entrano nel prompt in un blocco separato e dichiarato ("cose che hai
  detto TU — sono tue uscite, non fatti accertati"). Senza questa separazione,
  una persona che inventa di proposito si ricicla le invenzioni come verità.
- **Embedding**: oggi Chroma usa il modello di default (`all-MiniLM-L6-v2`,
  inglese). Con testo italiano un modello
  inglese ammassa tutto nella stessa zona dello spazio e il recupero diventa
  casuale. **Decisione da prendere** (§8): se Bea deve parlare italiano, il
  modello va cambiato in `paraphrase-multilingual-MiniLM-L12-v2` e i vettori
  esistenti ricalcolati (`rag.ensure_model`).
- **Migrazione**: script one-shot `tools/migrate_to_sqlite.py` che legge
  `roster.json`, `people.json`, `recent.json`, `self.md`, le 23 sessioni JSON e
  la collection Chroma, e popola il DB. Idempotente, con dry-run.
- I file JSON esistenti restano leggibili in sola lettura per un ciclo di
  rilascio, poi si rimuovono.

### 4.6 Piattaforme come Skill

Base comune per non riscrivere tre volte la stessa cosa:

```python
# src/core/skills/platform.py
class PlatformSkill(Skill):
    platform: str                                  # "discord" | "telegram" | "twitch"

    def build_author(self, raw: Any) -> Author: ...
    def conversation_key(self, meta: Dict) -> str  # f"{platform}:{channel_id}"
    async def emit_text(self, text: str, meta: Dict) -> List[str]   # via TextHumanizer
    def activity(self, channel_id: str, seconds: int) -> int        # per Attention
    def seconds_since_spoke(self, channel_id: str) -> Optional[float]
```

- **Discord**: adeguare `VoiceSurface` a questa base; aggiungere `/typing`.
- **Telegram** (nuovo, `src/core/skills/telegram/`): `python-telegram-bot` in
  polling, dentro il processo Python (nessun subprocess). Gli handler sono
  sottili: estraggono, costruiscono l'`Author`, depositano la perception.
- **Twitch** (nuovo): IRC read-only in prima battuta. Ogni messaggio aggiorna il
  roster (economico), ma **solo quelli che passano l'Attention arrivano alla
  mente**; il resto diventa una riga aggregata nel digest ("chat: 34 messaggi,
  parlano di X"). È letteralmente come un vero streamer percepisce la chat.
- **Donazioni**: webhook (StreamElements / Ko-fi) → perception con
  `Author.extra={"amount": ...}`, `is_addressed` → sempre `REACT`.

### 4.7 Minecraft su server vanilla: corpo **e** superficie sociale

> Questo è un obiettivo di prima classe: Bea deve giocare su un server vanilla
> **insieme ad altri giocatori** — leggere la chat, rispondere, reagire a quello
> che fanno, riconoscerli nel tempo. Non è "una skill in più": è la seconda
> arena sociale dopo Discord, e quella dove ha anche un corpo.

#### Verdetto sulla mod: è già pronta per il multiplayer

BeaCraft è un mod **client-side** Fabric 1.21.1. Non richiede nulla lato
server: per il server è un client normale. La domanda che conta è *come* esegue
le azioni, e la risposta è la migliore possibile.

| Azione | Come è implementata | Server vanilla |
|---|---|---|
| Movimento | `client.options.forwardKey.setPressed(true)` + yaw/pitch (`MoveSkill.java:412`) | ✅ input umano, pipeline vanilla |
| Rotazione | `RotationUtils.smoothAngle(…, 12°/tick)` + rumore sinusoidale ("respiro") (`MoveSkill.java:375,396`) | ✅ già umanizzata |
| Scavare | `client.options.attackKey.setPressed(true)` (`MineSkill.java:377`) | ✅ |
| Piazzare | `interactionManager.interactBlock` (`PlaceSkill.java:75`) | ✅ packet |
| Attaccare | `interactionManager.attackEntity` (`AttackSkill.java:419`) | ✅ packet |
| Inventario | `interactionManager.clickSlot` (~30 chiamate) | ✅ packet, autoritativo lato server |
| Craft | `clickRecipe` + `clickSlot` (`CraftingSkill.java:231,253`) | ✅ recipe book packet |
| Chat | `networkHandler.sendChatMessage` (`ChatSkill.java:19`) | ✅ |

**Due eccezioni** con rischio di desync, entrambe piccole e circoscritte:
`PillarSkill.java:83-84` e `MineDownSkill.java:66-67` chiamano `setPosition` per
centrare il giocatore sul blocco. È un teletrasporto sub-blocco: vanilla lo
tollera, un anticheat plugin no. Vanno riscritte come correzione di velocità.

Chi ha scritto la mod stava già pensando "deve sembrare un giocatore" — la
rotazione smussata con rumore lo dimostra. Il lavoro multiplayer quindi **non è
sulle azioni: è sui sensi**.

#### Il problema vero: in gioco Bea è sorda e cieca alle persone

Tre buchi verificati, tutti nella stessa direzione.

**1. Non riceve la chat.** `BeaCraftMod.onInitialize` (`BeaCraftMod.java:28-33`)
registra **solo** `ClientTickEvents`. Non c'è nessun
`ClientReceiveMessageEvents`: i messaggi degli altri giocatori non escono mai
dalla mod. Bea può parlare in chat ma non può leggerla.

**2. Il canale eventi è letteralmente vuoto.**
`GameStateGatherer.java:170` → `json.add("events", new JsonArray());`. Tutto ciò
che arriva a Python passa dai `broadcast` sparsi dei manager, e il lato Python
(`client.py:151-175`) riconosce **solo** `INTERRUPTED`, `FINISHED`, `IDLE` e i
pacchetti con la chiave `player`. Tutto il resto viene scartato in silenzio —
compreso l'evento di morte ricco (`DeathManager.java:123-159`, con causa,
coordinate e oggetti persi) e gli allarmi di autodifesa
(`SelfPreservationManager.java:202`).

**3. Gli altri giocatori sono indistinguibili dai mob.**
`GameStateGatherer.java:143-167` manda le entità entro 20 blocchi con `type`,
`name`, posizione, distanza e vita. Quindi un giocatore *appare*, ma:
- **senza UUID** → nessuna identità stabile su cui costruire memoria sociale;
- **senza distinzione esplicita** giocatore/mob;
- **solo entro 20 blocchi** → chi scrive in chat da lontano non esiste;
- **senza tab-list** → non sa chi è online.

#### Il guadagno architetturale: il sociale arriva gratis

Tutto lo stack sociale di Bea (roster, schede persona, promozione, iniezione
`[WHO YOU'RE TALKING TO]`, e la nuova Attention) è **keyato sull'`Author`**, non
sulla piattaforma. Quindi basta che il sensore Minecraft produca:

```python
Author(platform="minecraft", native_id=uuid, display_name="Marco")
```

e Bea ottiene **senza scrivere altro codice**: il tally nel roster, la
promozione a scheda quando Marco diventa un habitué, i fatti su di lui iniettati
quando è nei paraggi, `remember_person`, e il gate di attenzione che decide se
vale la pena rispondere. È la prova che l'astrazione del `PLAN.md` era giusta.

E un giocatore che è **anche** su Discord diventa esattamente il caso d'uso del
merge cross-platform (`PLAN.md` §5.5, Fase 7): stessa persona, due identità.

#### Come Bea percepisce il gioco: due flussi, non uno

`MinecraftSurface` emette perception con due `surface` diverse (una skill sola,
nessuna registrazione nuova — `Perception.surface` è una stringa libera):

| `surface` | Contenuto | `Author` | Attention di default |
|---|---|---|---|
| `chat:mc` | messaggi dei giocatori, whisper, join/leave, morti altrui | sì | `REACT` se la nomina o è vicina, altrimenti `NOTE` |
| `game:mc` | stato, milestone, interrupt del corpo | no | `NOTE`, tranne interrupt |

#### Parlare **o** scrivere: due atti diversi

È il punto che rende interessante Minecraft per una VTuber, e va reso esplicito
nel prompt e nei tool:

- **`speak(mood, message)`** → la sua **voce**, la sente il pubblico dello
  stream. È il commento: *"ma avete visto questo che mi ruba la legna"*.
- **`mc_chat(message)`** → quello che **digita in gioco**, lo leggono i
  giocatori. È la replica: *"quella era mia"*.

Sono due canali con due pubblici. Poterli usare **insieme nello stesso turno**
(commentare a voce e rispondere in chat) è esattamente il contenuto che si vuole
da una AI che gioca in multiplayer. Il vincolo di B5 (non parlare quando dovresti
scrivere) qui non si applica: qui servono davvero entrambi, ma consapevolmente.

#### Il corpo: sub-agente a obiettivi

Oggi la mente pilota il gioco tick per tick e ogni osservazione
(`FINISHED: SUCCESS`, JSON di stato) finisce nel context principale. Su un
server con gente che parla, questo affoga la personalità sotto i log del gioco.

La mente **decide un'intenzione**, il corpo la persegue, e riporta solo i
momenti che contano.

```python
# src/core/skills/minecraft/agent.py
class GameAgent:
    """Persegue un obiettivo usando i tool di gioco e il notebook.

    Usa AgentRunner (oggi codice morto: questa è la sua ragione d'essere)
    con il ruolo modello 'background'. Emette milestone via callback,
    non a ogni azione."""
    async def pursue(self, goal: str) -> str: ...
```

La mente vede **pochi tool**, non ventiquattro:

```python
play_minecraft(goal)            # long_running: dai un obiettivo al corpo
mc_chat(message)                # scrivi in chat di gioco
mc_stop()                       # smetti quello che stai facendo
mc_goto_player(name)            # raggiungi qualcuno
mc_follow_player(name)          # seguilo finché non smetti
mc_look_at_player(name)         # guardalo (fissare qualcuno è comunicazione)
mc_give_item(name, item, count) # avvicinati e buttagli le cose
```

Cosa torna alla mente come perception:
- **chat** (`chat:mc`): passa dall'Attention come qualunque altro messaggio;
- **milestone** (`salience 0.6`): "hai finito il piccone di pietra";
- **interrupt** (`salience 0.95`, sempre `REACT`): morte, danno **da un
  giocatore** (che è un evento sociale, non solo fisico), bloccata, lava;
- **snapshot periodico**: `NOTE`, mai `REACT`.

I 24 tool esistenti restano: cambiano consumatore. Li usa il `GameAgent`.

#### Costo del lidar (da sistemare nella stessa fase)

`GameStateGatherer.java:118-140` scandisce un cubo di raggio 4 (729 posizioni) e
manda **ogni blocco non-aria**, una volta al secondo. Sottoterra sono ~700 voci
JSON. Finisce dritto nel prompt. Va ridotto a ciò che serve davvero: superfici
calpestabili, ostacoli, blocchi di interesse (minerali, contenitori, liquidi),
e un riassunto per il resto ("circondata da pietra").

#### Nota operativa: dove far girare Bea

Un client che si muove e scava da solo è, tecnicamente, un client di
automazione (stessa categoria di Baritone). **Su un server proprio o
whitelistato con amici non c'è problema.** Su server pubblici l'automazione è
quasi sempre vietata dalle regole, e gli anticheat (Grim, NCP, Matrix) segnalano
il pathfinding e le rotazioni — a partire proprio dai due `setPosition` di
`PillarSkill`/`MineDownSkill`. Va deciso consapevolmente dove Bea gioca; il
piano assume **server proprio o privato**.

---

## 5. Bug e debiti verificati

Tutti riscontrati leggendo il codice. Ordinati per gravità.

### B1 · CRITICO · `GET /config` espone le chiavi API

`src/web/app.py:48-53` ritorna `asdict(brain.config)`, che include
`openrouter_key`, `openai_key`, `groq_key`, `orpheus_key`, `orpheus_endpoint`.
`save_to_file()` (`config.py:184-196`) le rimuove esplicitamente, l'endpoint no.

Aggravanti: CORS `allow_origins=["*"]` (`app.py:18-24`), bind su
`host="0.0.0.0"` (`server.py:5`), nessuna autenticazione su nessun endpoint.

**Impatto reale:** qualunque pagina web aperta nel browser mentre Bea gira può
fare `fetch("http://localhost:8000/config")` e leggere le chiavi. Se la porta è
raggiungibile dalla rete locale, chiunque sulla stessa LAN può leggerle senza
browser.

**Fix:** rimuovere i campi in `SECRET_KEYS` dalla risposta (riusare la stessa
lista di `save_to_file`, estraendola in un helper `config.public_dict()`);
default `host="127.0.0.1"`; CORS con allowlist esplicita; token statico in
header per gli endpoint di scrittura.

### B2 · ALTO · Il dreamer blocca l'intera coscienza

`src/core/skills/memory/generator.py:42` e `src/core/skills/dream/dreamer.py:96`
chiamano `self.llm.generate_json(...)`, che è **sincrono**
(`openai_compat.py:87` → `_create` → SDK bloccante) da dentro funzioni `async`.

L'event loop si ferma per tutta la durata della chiamata. Il dreamer
(`dreamer.py:60-89`) cicla su **tutte** le sessioni non ancora sognate, una
dopo l'altra: con 23 sessioni sono decine di chiamate in serie. Durante tutto
quel tempo Bea non sente, non parla, non risponde a Discord, e il bot node va
in timeout.

**Fix:** aggiungere `async def complete_json(...)` a `LLMClient` (`agent/llm_client.py`),
implementarlo in `OpenAICompatibleClient` con `asyncio.to_thread`, e convertire
i due chiamanti. Nel dreamer, `await asyncio.sleep(0)` fra una sessione e l'altra
non basta: serve che la chiamata stessa non blocchi.

### B3 · MEDIO · Il token Discord finisce in `config.json` in chiaro

`config.py:117` definisce `skills.discord.token`. `SECRET_KEYS`
(`config.py:144`) copre solo i campi di primo livello, e `save_to_file`
serializza l'intero dizionario `skills`. Ogni salvataggio dalla UI persiste il
token.

Mitigato dal fatto che `config.json` è in `.gitignore`, ma resta un segreto in
chiaro scritto da un'interfaccia web senza autenticazione (vedi B1).

**Fix:** togliere `token` dal dict `skills` (leggerlo solo da
`os.getenv("DISCORD_TOKEN")`, come già fa `transport.py:44` in prima battuta) e
mascherarlo nella risposta di `/config`.

### B4 · MEDIO · Il prompt promette un tool che non esiste

`data/prompts/operating.md` documenta `recall_memory(query)`, ma
`MemorySkill.tools()` (`memory/memory.py:87-91`) ritorna `[]` — il tool è stato
rimosso nel commit `25fad39` e il prompt non è stato aggiornato.

Il modello proverà a chiamarlo e riceverà `ERROR: unknown tool 'recall_memory'`,
bruciando un passo di burst.

**Fix:** rimuovere la riga dal prompt. (E in generale: i prompt vanno considerati
codice — vanno aggiornati nello stesso commit del tool che descrivono.)

### B5 · MEDIO · Su testo Discord senza correlazione, Bea parla ad alta voce

`consciousness.py:317-327`. Le perception di testo Discord arrivano via
`perceive_discord_text` **senza** `correlation_id` (`brain.py:286-296`), quindi
`routes` è vuoto: `"discord" in routes` è falso e si entra nel ramo locale →
`speak` va al TTS e agli altoparlanti invece che in chat.

Oggi l'unico argine è la regola nel prompt (`voice/surface.py:105-108`). Un
modello che sbaglia produce una Bea che risponde a voce a un messaggio scritto.

**Fix:** rendere il routing strutturale, non testuale. La `Verdict`
dell'Attention porta con sé il canale d'origine; `_speak` rifiuta (o reindirizza)
se il batch non contiene nulla di "palco". Con i conversation turn (§4.2) il
problema sparisce per costruzione: quei turni non hanno il tool `speak`.

### B6 · MEDIO · `_run_body` etichetta tutto come Minecraft

`consciousness.py:305-308`: qualunque tool `long_running` produce una perception
con `surface="game:mc"`. Appena esisterà una seconda body action (o il
`GameAgent`), i risultati saranno mal attribuiti.

**Fix:** `Tool` porta il `surface` di appartenenza, oppure `_dispatch_body`
riceve la skill che ha registrato il tool.

### B7 · MEDIO · Riscrittura O(N) del roster a ogni messaggio

`social/roster.py:89` — `record()` chiama `_save()`, che serializza **l'intero**
dizionario. `SocialMemory.context_for` (`social.py:45-61`) chiama `record()` per
ogni perception con autore. Con 5.000 chatter Twitch, ogni messaggio riscrive
5.000 record.

Risolto strutturalmente dalla Fase 4 (SQLite). Mitigazione immediata se serve
prima: scrittura differita con debounce.

### B8 · BASSO · Heartbeat Minecraft da 10 secondi

`minecraft/surface.py:73-80`. Vedi G1. Risolto dall'Attention (Fase 1):
gli snapshot senza eventi diventano `NOTE`.

### B9 · BASSO · Tool registry ricostruito a ogni passo

`consciousness.py:275` e `:279`. Costruzione completa del registry per gli
schemi e un'altra per ogni dispatch.

**Fix:** cache invalidata quando cambia l'insieme delle skill attive
(`set_surface_active` è l'unico punto che lo modifica).

### B10 · BASSO · `surface_registry` dereferenziato senza guardia

`brain.py:237`, `:250`, `:278`, `:293`. `app.py:313` la guardia ce l'ha, il
brain no. `AttributeError` se qualcuno chiama gli entrypoint prima di
`initialize()`.

### B11 · BASSO · `AgentRunner` è codice morto

`src/core/agent/runner.py` (106 righe) non è mai istanziato. O gli si dà il
lavoro previsto dalla Fase 8 (`GameAgent`), o si cancella. Non lasciarlo lì.

### B12 · `docs/architecture.md` descrive un'architettura che non esiste più

Parla di `SkillManager`, `_is_backchannel`, `resume_buffer` nel brain, path
reattivi legacy — tutto rimosso nei commit `84139a3` e `8711a59`. Un agente che
lo legge per orientarsi parte con un modello mentale sbagliato del sistema.

### B13 · Nessun test, nessun lint, nessuna CI

`pyproject.toml` non ha né `pytest`, né `ruff`, né dipendenze di sviluppo. Per
Servono test proprio sulle parti che qui
stiamo per riscrivere.

### B14 · ALTO (Minecraft) · Bea non riceve la chat di gioco

`beacraft/…/BeaCraftMod.java:28-33` registra solo `ClientTickEvents`. Nessun
`ClientReceiveMessageEvents` → i messaggi degli altri giocatori non lasciano mai
la mod. In multiplayer Bea può scrivere ma non può leggere: è muta a metà.

**Fix:** nuovo `ChatListener.java` (Fase 8A).

### B15 · ALTO (Minecraft) · Metà degli eventi della mod viene scartata in silenzio

Lato mod, i manager mandano eventi ricchi con `ActionManager.broadcast(...)`.
Lato Python, `MinecraftClient._handle` (`client.py:151-175`) riconosce **solo**
i pacchetti con la chiave `player` e gli `status` `INTERRUPTED`/`FINISHED`/`IDLE`.
Tutto il resto cade nel vuoto:

| Cosa va perso | Origine |
|---|---|
| evento morte completo (causa, coordinate, oggetti persi) | `DeathManager.java:123-159` — manda `{"type":"death_event"}`, **senza** campo `status` |
| autodifesa ingaggiata | `SelfPreservationManager.java:202` — `status: "ENGAGED_AUTO_ACTION"` |

Effetto concreto: Bea sa di essere stata "INTERRUPTED", ma non sa **di essere
morta, come, dove, né cosa ha perso** — mentre il dato esiste già ed è pronto.

**Fix:** dispatch per `type` in `_handle`, non solo per `status` (Fase 8B).

### B16 · MEDIO (Minecraft) · Gli altri giocatori non hanno identità

`GameStateGatherer.java:141-167` manda le entità con `name` ma **senza UUID** e
senza distinguere giocatori da mob; raggio 20 blocchi; nessuna tab-list.
Senza un id nativo stabile non si può costruire nessun `Author`, e quindi tutto
lo stack sociale (roster, schede, attenzione) resta spento in Minecraft.

### B17 · MEDIO (Minecraft) · Il lidar costa una fortuna in token

`GameStateGatherer.java:118-140`: cubo di raggio 4 (729 posizioni), **tutti** i
blocchi non-aria, ogni secondo. Sottoterra ~700 voci JSON che finiscono nel
system prompt. Va filtrato per rilevanza e riassunto.

### B18 · BASSO (Minecraft) · Due teletrasporti che l'anticheat può segnalare

`PillarSkill.java:83-84` e `MineDownSkill.java:66-67` usano `setPosition` per
centrarsi sul blocco. Sub-blocco, quindi vanilla lo tollera, ma è l'unica cosa
in tutta la mod che non passa dagli input. Da riscrivere come correzione di
velocità prima di giocare su un server con anticheat.

### B19 · BASSO (Minecraft) · Il WebSocket della mod è aperto sulla LAN senza auth

`BeaCraftMod.java:118` fa il bind su `0.0.0.0:8080` senza autenticazione:
chiunque sulla stessa rete può connettersi e **pilotare il client Minecraft**.
Bind su `127.0.0.1` (il brain gira in locale) o token condiviso nell'handshake.

---

## 6. Piano a fasi

Ogni fase è **indipendente, rilasciabile e testabile da sola**. L'ordine è per
rapporto valore/rischio: prima si tolgono i piedi dalle mine (Fase 0), poi si fa
il cambiamento con più impatto (Fase 1), poi si costruisce.

Convenzione: ✅ **Definition of done** chiude ogni fase. Se non è verificabile,
non è fatta.

---

### Fase 0 — Igiene (mezza giornata, blocca tutto il resto)

**Obiettivo:** non costruire su fondamenta che perdono chiavi API e congelano la
mente.

| # | Cosa | File |
|---|---|---|
| 0.1 | `config.public_dict()` che rimuove `SECRET_KEYS` + maschera `skills.discord.token`; usarlo in `GET /config` | `src/core/config.py`, `src/web/app.py:48` |
| 0.2 | Default `host="127.0.0.1"`; flag `--host` per esporre di proposito; CORS con allowlist | `src/web/server.py`, `src/web/app.py:18` |
| 0.3 | `async def complete_json()` su `LLMClient` (via `asyncio.to_thread`); migrare `DiaryGenerator` e `Dreamer` | `agent/llm_client.py`, `modules/llm/openai_compat.py`, `memory/generator.py:42`, `dream/dreamer.py:96` |
| 0.4 | Togliere `recall_memory` da `operating.md` | `data/prompts/operating.md` |
| 0.5 | Guardie `None` su `surface_registry` | `src/core/brain.py:237,250,278,293` |
| 0.6 | Dev tooling: `pytest`, `pytest-asyncio`, `ruff` in un dependency group; target `make test` / `make lint` | `pyproject.toml`, `Makefile` |
| 0.7 | Primi test sulla logica pura già esistente: `should_promote`/`promotion_reason` (`social/people.py:21-43`), `RecentStore` TTL (`dream/recent.py`), `prompts.compose`, `_days_until` | `tests/` |
| 0.8 | Riscrivere `docs/architecture.md` sull'architettura reale (o ridurlo a un puntatore a questo documento) | `docs/architecture.md` |
| 0.9 | Cancellare `AgentRunner` **oppure** annotarlo come "riservato alla Fase 8" | `src/core/agent/runner.py` |

✅ **Done:** `curl localhost:8000/config | grep -i key` non restituisce segreti;
`make test` verde con ≥8 test; un dream pass non blocca una risposta in chat
(verificabile: lancia `/dream/run` e manda un messaggio, deve rispondere).

---

### Fase 1 — Attention (2-3 giorni) ⭐ massimo impatto

**Obiettivo:** Bea smette di deliberare su tutto. Reagisce a ciò che la riguarda,
registra il resto.

**Nuovi file:**
```
src/core/attention/__init__.py
src/core/attention/types.py     Reaction, Verdict          (puro)
src/core/attention/rules.py     is_addressed, score, in_quiet_hours  (puro)
src/core/attention/gate.py      Attention                  (stato + rng + clock iniettabili)
src/utils/text_match.py         match a parola intera, puro
tests/test_attention_rules.py
tests/test_attention_gate.py
tests/test_text_match.py
```

**Modifiche:**
- `consciousness.py:133-160` — le tre righe di §4.1.
- `consciousness.py:241` — il digest entra in `parts`.
- `consciousness.py:312` — `mark_spoke()`.
- `brain.py:124` — costruire `Attention` e passarla alla `Consciousness`.
- `config.py` — blocco `attention` (§4.1).
- `minecraft/surface.py:79` — gli snapshot senza eventi scendono a `salience 0.15`
  e vengono marcati `noise=True` in `meta`.

**Contratto da rispettare:** `rules.py` non importa nulla di asyncio, di rete o di
`Skill`. Prende primitivi, ritorna un float. È la condizione per poterlo testare
a tabella.

**Osservabilità (non opzionale):** ogni `Verdict` va pubblicato come
`EventCategory.SYSTEM` con `metadata={"reaction","score","reason"}`, e la pagina
Brain Activity deve mostrarlo. Senza vedere *perché* ha ignorato qualcosa, la
taratura delle soglie è alla cieca.

✅ **Done:** con Minecraft acceso e nessuno che parla, il conteggio delle chiamate
LLM in 10 minuti scende da ~60 a ≤3. Un messaggio Discord con menzione ottiene
sempre risposta. Il dashboard mostra le decisioni di attenzione. ≥20 test sulle
funzioni pure.

---

### Fase 2 — Testo umano (1-2 giorni)

**Obiettivo:** quando Bea scrive, sembra che scriva una persona.

**Nuovi file:**
```
src/utils/sanitize.py                    pulizia dell'output del modello
src/core/expression/__init__.py          (Expression si sposta qui)
src/core/expression/humanizer.py         consegna del testo, riga per riga
tests/test_sanitize.py
tests/test_humanizer.py
```

**Modifiche:**
- `openai_compat.py:60` — `content=clean_model_output(message.content)`.
- `consciousness.py:312` — sanificare `message` prima del TTS.
- `voice/surface.py:215-220` — `discord_send_message` / `discord_reply` passano
  per l'humanizer.
- `bot/api/server.js` — nuovo `POST /typing {channelId}` → `channel.sendTyping()`.
- `voice/transport.py` — metodo `typing(channel_id)`.

**Attenzione al dettaglio:** la trascrizione salvata in storia
deve essere **ciò che è partito davvero**, non il testo generato. Se un chunk non
parte, non deve comparire nella storia (`humanizer.deliver` ritorna la lista dei
chunk inviati proprio per questo).

✅ **Done:** una risposta Discord multi-riga arriva come messaggi separati con
"sta scrivendo" fra l'uno e l'altro; un output con `<think>...</think>` non
viene mai pronunciato né scritto; ≥15 test.

---

### Fase 3 — Registry a ruoli (1 giorno)

**Obiettivo:** un provider giù non fa ammutolire Bea; il lavoro di background non
compete con la mente.

**Nuovi file:** `src/core/agent/registry.py`, `tests/test_registry.py`.

**Modifiche:**
- `cli.py:141` — `registry = ModelRegistry(config, stt)`; `brain` riceve il
  registry invece del singolo client.
- `brain.py` — `self.llm = registry.get("mind")`; espone `registry` alle skill.
- `memory/memory.py:76`, `dream/surface.py:58` — usano `registry.get("background")`.
- `config.py` — blocco `models` (§4.4); i vecchi campi `*_model` restano come
  fallback per retrocompatibilità.

**Test da scrivere:** ordine di rotazione su N
chiamate; fallback quando il primo client solleva; errore chiaro quando il pool
è vuoto; rispetto del vincolo tool-calling.

✅ **Done:** con una chiave OpenRouter invalida e una Groq valida, Bea continua a
funzionare e il log dice quale modello ha preso; il dream pass gira sul modello
`background`.

---

### Fase 4 — Memoria su SQLite (3-5 giorni)

**Obiettivo:** un solo store transazionale, che regge una audience e sa
distinguere i fatti dalle invenzioni di Bea.

**Nuovi file:**
```
src/core/memory/db.py             SQLite (WAL, lock, sqlite-vec opzionale)
src/core/memory/schema.sql        lo schema di §4.5
src/core/memory/store.py          facciata (people, roster, messages, summaries)
src/core/memory/rag.py            recall con recall_split
src/core/memory/embedder.py       fastembed locale
tools/migrate_to_sqlite.py        one-shot, idempotente, con --dry-run
tests/test_memory_store.py
tests/test_rag.py
```

**Ordine di lavoro consigliato:** prima lo store + la migrazione con i vecchi
lettori ancora attivi in sola lettura; poi si spostano i consumatori uno alla
volta (roster → people → hot facts → self → diario); infine si rimuovono i JSON.

**Aggiunta funzionale della fase** (non solo un porting): il **riassunto rolling
per conversazione** e il **profilo persona a trigger di conteggio**, presi da
Sono ciò che dà
la sensazione "sa chi sei" senza aspettare un dream: la prima scheda si fa
presto (20 messaggi), gli aggiornamenti sono radi (50), e girano sul modello
`background` **dopo** aver risposto, così non pesano sul turno.

✅ **Done:** `data/bea.db` contiene tutto ciò che c'era nei JSON e in Chroma;
i vecchi file non vengono più scritti; un recall restituisce due blocchi
distinti (fatti / sue uscite); ≥25 test.

---

### Fase 5 — Concorrenza: live loop + conversation turns (3-4 giorni)

**Obiettivo:** parlare con più persone su più piattaforme senza accodare tutto
dietro un turno solo.

**Nuovi file:**
```
src/core/mind/__init__.py
src/core/mind/scheduler.py        un turno per conversazione, in parallelo
src/core/mind/conversation.py     ConversationTurn: costruzione context + esecuzione
tests/test_scheduler.py
tests/test_conversation_context.py
```

**Modifiche:** `Consciousness` si specializza in *live loop*; l'Attention
instrada: le perception con un `conversation_key` che non è `"stage"` vanno allo
scheduler come conversation turn, il resto al live loop.

**I due punti delicati** — segnalarli a chi implementa:
1. **Nessuna doppia risposta.** Una perception va a *un* turno soltanto. Il
   routing deve essere una `if/else` esplicita, non due consumatori dello stesso
   batch.
2. **Il digest è condiviso, il context no.** `[ALTRE CONVERSAZIONI]` e
   `[COSA STAI FACENDO ADESSO]` sono **una riga ciascuno**. Se si comincia a
   travasare context fra turni si torna al problema di partenza con più
   complessità.

✅ **Done:** due conversazioni Discord in canali diversi ricevono risposta in
parallelo; tre messaggi ravvicinati nello stesso canale producono **una** sola
risposta; l'ordine dentro un canale è sempre rispettato; ≥12 test.

---

### Fase 6 — Telegram (2 giorni)

**Obiettivo:** la seconda piattaforma testuale, e la prova che
`PlatformSkill` è un'astrazione vera.

**Nuovi file:**
```
src/core/skills/platform.py               base comune (§4.6)
src/core/skills/telegram/__init__.py
src/core/skills/telegram/surface.py       TelegramSkill(PlatformSkill)
src/core/skills/telegram/handlers.py      sottili: estrai, deposita, esci
tests/test_telegram_routing.py
```

Dipendenza: `python-telegram-bot[job-queue]`. Gira **in-process** con
`Application.builder().concurrent_updates(True)`, avviata da `start()` della
skill — niente subprocess (a differenza di Discord, dove il subprocess node
serve per la voce).

Riusare: `is_bot_called` e
la logica di follow-up già portata in Fase 1.

✅ **Done:** Bea risponde in un gruppo Telegram quando chiamata; interviene
spontaneamente secondo l'Attention; i DM contano come 1:1 nel roster e portano
la promozione a scheda persona.

---

### Fase 7 — Twitch e donazioni (2-3 giorni)

**Obiettivo:** la chat ad alto volume, che è il vero test dell'Attention.

- `src/core/skills/twitch/surface.py` — IRC read-only (`twitchio` o socket +
  IRC grezzo: la seconda opzione toglie una dipendenza pesante).
- **Ogni** messaggio aggiorna il roster (ora è una `INSERT` su SQLite, non una
  riscrittura). **Solo** i messaggi che passano l'Attention arrivano alla mente.
- Il resto viene aggregato: una riga di digest ogni N secondi con conteggio e,
  opzionalmente, i tre termini più frequenti.
- `src/core/skills/donation/surface.py` — endpoint webhook
  `POST /webhook/donation`, `Author.extra={"amount", "currency", "message"}`,
  `is_addressed` → sempre `REACT`, promozione immediata a scheda persona (regola
  già presente in `people.py:21-31`).

✅ **Done:** con 30 messaggi/minuto simulati, le chiamate LLM restano sotto le 4
al minuto e Bea risponde comunque a chi la nomina; una donazione ottiene sempre
una reazione entro un turno.

---

### Fase 8 — Minecraft su server vanilla con altri giocatori (8-11 giorni)

**Obiettivo:** Bea entra in un server vanilla insieme ad altre persone, legge la
chat, risponde, reagisce a quello che fanno, li riconosce nel tempo, e nel
frattempo gioca davvero.

È la fase più grande del piano ed è divisa in quattro sotto-fasi **rilasciabili
una alla volta**. Le prime due (8A e 8B) danno già il 70% del risultato
percepito: una Bea che *parla con la gente in gioco* vale più di una Bea che
costruisce bene da sola.

> ⚠️ **Prerequisito non tecnico:** decidere dove gioca. Il piano assume un
> server **proprio o whitelistato**. Vedi la nota operativa in §4.7.

---

#### Fase 8A — I sensi: la mod impara a sentire (2-3 giorni, Java)

Tutto nella mod. Nessuna modifica al comportamento: solo dati in più che
escono dal WebSocket. Testabile da sola con `websocat` senza toccare Python.

**Nuovo file `ChatListener.java`**, registrato in `BeaCraftMod.onInitialize`:

```java
ClientReceiveMessageEvents.CHAT.register((message, signed, sender, params, ts) -> {
    // sender è una GameProfile: qui c'è l'UUID, ed è l'unica fonte affidabile
    broadcastChat("player", sender, message.getString());
});
ClientReceiveMessageEvents.GAME.register((message, overlay) -> {
    if (overlay) return;                    // action bar: non è chat
    broadcastChat("system", null, message.getString());
});
```

Formato dei nuovi pacchetti (tutti con `type`, così Python può fare dispatch):

```json
{"type":"chat","kind":"player","author":{"uuid":"…","name":"Marco"},
 "text":"ciao bea","ts":1699999999}
{"type":"chat","kind":"system","text":"Marco joined the game","ts":…}
{"type":"player_event","event":"join|leave","player":{"uuid":"…","name":"…"}}
{"type":"combat","event":"hurt","source":"player|mob|fall","by":{"uuid":"…","name":"…"},
 "health":12.0}
```

**Modifiche a `GameStateGatherer.java`:**

| # | Cosa | Perché |
|---|---|---|
| 8A.1 | Su ogni entità di tipo giocatore aggiungere `uuid` e `is_player: true` | senza UUID non esiste `Author` (B16) |
| 8A.2 | Nuovo blocco `players_online[]` dalla tab-list (`networkHandler.getPlayerList()`) | sapere chi c'è, anche lontano |
| 8A.3 | Filtrare il lidar: superfici calpestabili, ostacoli, blocchi *interessanti* (minerali, contenitori, liquidi, crafting); il resto diventa un riassunto (`"circondata da: stone ×612, dirt ×88"`) | B17 |
| 8A.4 | Dare un `status` al `death_event` di `DeathManager` | B15 |
| 8A.5 | Bind del WebSocket su `127.0.0.1` | B19 |
| 8A.6 | `PillarSkill`/`MineDownSkill`: `setPosition` → correzione di velocità | B18 |

✅ **Done:** con `websocat ws://127.0.0.1:8080` collegato, scrivere in chat da un
altro account produce un pacchetto `type:"chat"` con UUID corretto; entrare e
uscire dal server produce `player_event`; il payload di stato scende sotto i
4 KB anche sottoterra.

---

#### Fase 8B — Bea sociale in gioco (2-3 giorni, Python)

**Il pezzo che dà più risultato di tutta la fase.** Qui la chat di Minecraft
entra nello stack sociale già esistente e Bea comincia a comportarsi da persona
che gioca con altre persone.

`src/core/skills/minecraft/client.py` — `_handle` fa dispatch su `type` **prima**
che su `status` (risolve B15):

```python
def _handle(self, data):
    kind = data.get("type")
    if kind == "chat":         return self._on_chat(data)
    if kind == "player_event": return self._on_player_event(data)
    if kind == "combat":       return self._on_combat(data)
    if kind == "death_event":  return self._on_death(data)
    ...                        # status esistenti, invariati
```

`src/core/skills/minecraft/surface.py` — nuovo emettitore di perception sociali:

```python
def _emit_chat(self, uuid: str, name: str, text: str, whisper: bool = False):
    author = Author(platform="minecraft", native_id=uuid, display_name=name)
    self.bus.put(Perception(
        kind=PerceptionKind.CHAT,
        surface="chat:mc",                     # ≠ "game:mc": è sociale, non corporeo
        content=f"[{name}] (in game): {text}",
        salience=0.9 if whisper else 0.7,
        meta={"uuid": uuid, "whisper": whisper,
              "conversation_key": "minecraft:server"},
        author=author,
    ))
```

Da qui in avanti **non serve altro codice** per avere: tally nel roster,
promozione a scheda quando Marco diventa un habitué, iniezione dei fatti su di
lui quando è nei paraggi, `remember_person`, e il gate di attenzione. Tutto lo
stack è già keyato sull'`Author`.

Regole di attenzione specifiche (in `attention/rules.py`):
- `is_addressed` → whisper diretto, oppure il testo contiene un trigger word,
  oppure chi parla è a meno di ~6 blocchi e ha appena parlato;
- `combat` con `source: "player"` → **sempre** `REACT`: uno che ti picchia è un
  evento sociale, non un danno;
- morte → sempre `REACT`, e con il contesto ricco (chi, dove, cosa hai perso);
- chat generica lontana → `NOTE`, finisce nel digest.

**Prompt** (`data/prompts/minecraft.md`): aggiungere la sezione sui due canali
(voce per il pubblico / `mc_chat` per i giocatori) descritta in §4.7. È la parte
che va tarata a mano guardandola dal vivo.

✅ **Done:** su un server con un secondo account, scrivere "bea vieni qui" ottiene
una risposta in chat di gioco; scrivere qualcosa che non la riguarda non produce
nessuna chiamata LLM; dopo tre sessioni con la stessa persona compare la sua
scheda in `people`; se un giocatore la colpisce, reagisce.

---

#### Fase 8C — Interazione fisica con le persone (2 giorni)

I tool che trasformano "risponde in chat" in "gioca *con* te". Ogni tool Python
ha bisogno della sua skill Java corrispondente.

| Tool (mente) | Skill Java | Nota |
|---|---|---|
| `mc_goto_player(name)` | riusa `MoveSkill` con target dinamico | il bersaglio si muove: ricalcolo periodico |
| `mc_follow_player(name)` | nuova `FollowSkill` | mantiene 2-4 blocchi, si ferma da sola se lo perde |
| `mc_look_at_player(name)` | `LookSkill` esteso a entity id | fissare qualcuno è comunicazione |
| `mc_give_item(name, item, count)` | `MoveSkill` + `DiscardSkill` | vanilla non ha "give": ci si avvicina e si buttano le cose |
| `mc_stop()` | `ActionManager.stop` | esiste già, va solo esposto |

✅ **Done:** "vieni qui" → arriva; "seguimi" → segue finché non le si dice basta;
"dammi del legno" → si avvicina e lo butta per terra.

---

#### Fase 8D — Il corpo a obiettivi (2-3 giorni)

Solo ora conviene fare il `GameAgent`: prima si guadagna il sociale, poi si
ripulisce il context.

- `src/core/skills/minecraft/agent.py` — `GameAgent` su `AgentRunner` (§4.7),
  modello `background`, notebook, milestone via callback.
- `MinecraftSurface.tools()` espone alla mente i 7 tool di §4.7 invece di 25;
  i 24 tool di gioco passano al `GameAgent`.
- `data/prompts/minecraft.md` si sdoppia: la survival guide e la catena di
  crafting vanno al sub-agente; alla mente resta una `context_section` breve
  ("hai un corpo in Minecraft, puoi dargli un obiettivo e commentare").
- Le milestone rientrano con la `surface` corretta (risolve **B6**).

✅ **Done:** Bea completa "prendi un piccone di pietra" mentre risponde a tre
messaggi in chat di gioco e a uno su Discord; il context principale non contiene
JSON di stato di gioco.

---

### Fase 9 — Ritmo di vita (2 giorni)

**Obiettivo:** una giornata, non un ciclo di eventi.

- `spontaneous.py`: job periodico che, nelle conversazioni
  vive, fuori dalle quiet hours e dopo abbastanza silenzio, ogni tanto **inizia**
  qualcosa. Bea oggi può solo monologare sul palco.
- Dreamer su schedule notturno, non solo a comando.
- Il `morning_pass` (già esistente, `dream/surface.py:85`) si estende con "cosa
  è successo ieri" preso dai riassunti.

✅ **Done:** lasciata sola per un'ora in un gruppo attivo, Bea scrive di sua
iniziativa al massimo una volta e in modo pertinente; il dream gira di notte
senza intervento.

---

### Fase 10 — Osservabilità (1 giorno)

- `GET /events/stream` in SSE al posto del polling a 2 secondi
  (`SkillsPage.jsx:45`, `BrainActivityPage.jsx`).
- Contabilizzazione token per turno, esposta in Brain Activity.
- Pannello Attention: ultime N decisioni con punteggio e motivo.

---

### Riepilogo dipendenze fra fasi

```
Fase 0 (igiene) ─┬─▶ Fase 1  Attention ──┬─▶ Fase 5  Concorrenza ─┬─▶ Fase 6  Telegram
                 │                        │                        └─▶ Fase 7  Twitch
                 ├─▶ Fase 2  Testo ───────┤
                 │                        └─▶ Fase 8B Bea sociale in gioco
                 ├─▶ Fase 3  Registry ──▶ Fase 4  SQLite ──────────▶ Fase 9  Ritmo
                 │                                    │
                 └─▶ Fase 8A Sensi mod (Java) ────────┴─▶ 8C Interazione ─▶ 8D Corpo
                        (indipendente da tutto)
                                                              Fase 10 (quando serve)
```

- **8A non dipende da niente**: è tutta Java, si può fare in parallelo a
  qualunque altra cosa, anche subito dopo la Fase 0.
- **8B richiede la Fase 1** (l'Attention) e la **Fase 8A**: senza il gate, la
  chat di un server pieno di gente farebbe partire una chiamata LLM a messaggio.
- 1, 2, 3 e 8A sono parallelizzabili fra loro se ci lavorano persone diverse.
- La 4 conviene farla dopo la 3 (usa il ruolo `background`).

### Il percorso più corto verso "Bea gioca in vanilla con altri"

Se l'obiettivo Minecraft-multiplayer viene prima di tutto il resto, il cammino
minimo è:

```
Fase 0  →  Fase 1  →  Fase 8A  →  Fase 8B      ≈ 8-10 giorni
```

Alla fine di questo percorso Bea è già in un server vanilla, legge la chat,
risponde in chat, riconosce chi torna, reagisce a chi la colpisce, e commenta a
voce per il pubblico dello stream — pur muovendosi ancora coi 24 tool attuali.
8C e 8D la rendono migliore *come giocatrice*, non *come persona*: vengono dopo.

**Non saltare la Fase 1.** In singleplayer se ne può fare a meno; su un server
con altre persone la chat è continua, e senza gate ogni messaggio è una chiamata
LLM: costo insostenibile, latenza crescente, e una Bea che commenta ogni singola
riga come un bot.

---

## 7. Strategia di test

La regola che rende testabile un progetto:

> **Le decisioni sono funzioni pure. Gli effetti sono iniettati.**

Applicata concretamente:

| Cosa | Come si testa |
|---|---|
| `attention/rules.py` | tabella di casi → punteggio atteso |
| `attention/gate.py` | `rng` e `clock` iniettati nel costruttore |
| `humanizer.split/delay_for` | stringa → lista di chunk attesa |
| `humanizer.deliver` | `send_text`/`send_typing` finti che registrano |
| `sanitize` | input sporchi noti → output pulito |
| `ConversationScheduler` | turni finti, verifica ordine e accorpamento |
| `RotatingClient` | client finti, uno che solleva |
| memoria / RAG | DB in-memory + embedder finto deterministico |
| coscienza | `LLMClient` finto che ritorna `AssistantMessage` prefabbricate |

**Il pezzo che manca a entrambi i progetti** e che va costruito qui: un
`FakeLLMClient` che, data una sequenza di `AssistantMessage`, permetta di
testare il loop della coscienza end-to-end senza rete. Con quello si possono
scrivere test tipo "se arriva una perception di gioco e una di chat, la mente
chiama `speak` una volta sola" — oggi impossibili.

Setup minimo (Fase 0):

```toml
[dependency-groups]
dev = ["pytest", "pytest-asyncio", "ruff"]
```

```makefile
test: ## run the test suite
	uv run pytest -q

lint: ## static checks
	uv run ruff check src tests
```

Obiettivo di copertura: **non** una percentuale globale. La regola è: *ogni
funzione pura nuova nasce con i suoi test nello stesso commit*. Il resto
(integrazione con Discord, OBS, TTS) si verifica a mano.

---

## 8. Decisioni aperte

Da chiudere prima di implementare la fase corrispondente. Ognuna cambia il
lavoro in modo non banale.

**D1 · Lingua di Bea.** Il soul è in inglese, il proprietario parla italiano.
Se Bea deve reggere l'italiano, il modello di embedding va cambiato in
multilingua (§4.5) e i prompt vanno rivisti. → decidere prima della **Fase 4**.

**D2 · Confine dei conversation turn.** La proposta (§4.2) è: niente `speak`,
niente body action, solo i tool della piattaforma. Alternativa: un turno può
"salire sul palco" chiedendo alla mente. La seconda è più espressiva e più
rischiosa. → decidere prima della **Fase 5**.

**D3 · Twitch: quanto aggregare.** Una riga di digest ogni N secondi, oppure un
riassunto LLM della chat ogni M minuti (costa, ma è molto più ricco). → **Fase 7**.

**D4 · Taratura dei prompt.** I meccanismi si importano, i prompt **no**: il
`soul.md` resta intoccabile (regola del `PLAN.md`, §9). Va deciso se e come
tarare i prompt operativi sul modello che si userà davvero.

**D5 · Il subprocess node di Discord.** Con Telegram in-process, restare a due
runtime solo per la voce Discord è un costo operativo. Alternativa: `discord.py`
con `PyNaCl` per la voce, tutto in Python, un processo solo. È un lavoro di
2-3 giorni e cancella ~1.000 righe di JS. → valutare dopo la **Fase 6**.

**D6 · Su quale server gioca Bea.** Il piano assume un server **proprio o
whitelistato con amici**: un client di automazione su server pubblici viola
quasi sempre le regole e viene segnalato dagli anticheat (§4.7). Va deciso
prima della **Fase 8A**, perché cambia quanto lavoro mettere nel rendere il
movimento indistinguibile da quello umano.

**D7 · Bea usa un account Minecraft proprio.** Serve un account dedicato (non
quello personale) e, se il server è online-mode, credenziali proprie. Da
sistemare prima della Fase 8B, insieme a come tenerle fuori dal repository.

**D8 · Persistenza dei conversation turn.** I turni scoped hanno bisogno di una
loro storia (ultimi N messaggi per canale). Riusa `messages` di §4.5, ma va
deciso il TTL: quanto indietro tenere la storia di un canale Twitch.

---

## 9. Anti-pattern

Riprendono e integrano quelli del `PLAN.md` §9. Sono qui perché sono i modi
concreti in cui questo progetto può peggiorare.

- **Non far decidere a un LLM *se* rispondere.** L'Attention è euristica per
  motivi di costo e latenza. Una chiamata LLM per decidere se fare una chiamata
  LLM raddoppia il costo e aggiunge un secondo di ritardo a ogni stimolo.
- **Non far evolvere `soul.md` in automatico.** Vale ancora. Ciò che evolve va
  in `self.md` / People / Recent.
- **Non far crescere la memoria senza dimenticare.** Senza pruning, fra mesi il
  retrieval peggiora. Il dedup dei diari (`PLAN.md` §5.4.6) è ancora da fare.
- **Non unire identità in automatico.** Meglio due persone separate che una
  sbagliata (`PLAN.md` §5.5).
- **Non mettere logica dentro `Consciousness`.** È già a 386 righe. Ogni pezzo
  nuovo (attenzione, routing, scheduling) va in un modulo suo con un'interfaccia
  stretta. Se `consciousness.py` supera le ~450 righe, qualcosa è nel posto
  sbagliato.
- **Non aggiungere tool alla mente senza toglierne.** Ogni tool armato è
  descrizione nel prompt e possibilità di errore. La Fase 8 ne toglie 24 e ne
  aggiunge 1: è la direzione giusta.
- **Non toccare i prompt senza toccare il codice, e viceversa.** B4 è nato così.
  Prompt e tool si modificano nello stesso commit.
- **Non copiare un bot request-reply alla lettera.** Vive su una sola piattaforma.
  Si prendono i componenti puri (score, split, sanitize, scheduler, rotazione),
  non il flusso.

---

## 10. Appendice: punti d'innesto e contratti

### 10.1 Mappa rapida

| Cosa | Dove |
|---|---|
| Registrare una skill nuova | `src/core/brain.py:129` (lista `skill_cls`) |
| Ciclo della mente | `src/core/consciousness.py:133` |
| Costruzione del system prompt | `src/core/consciousness.py:224` |
| Tool sempre disponibili (`speak`, `stay_silent`) | `src/core/consciousness.py:253` |
| Body action async | `src/core/consciousness.py:289` |
| Output vocale + OBS | `src/core/expression.py:60` |
| Barge-in / resume | `src/core/expression.py:255` |
| Coalescing delle perception | `src/core/perception/bus.py:38` |
| Autore strutturato | `src/core/perception/types.py:20` |
| Toggle skill da UI | `src/core/brain.py:150` → `consciousness.set_surface_active` |
| Client LLM tool-aware | `src/modules/llm/openai_compat.py:32` |
| Endpoint HTTP | `src/web/app.py` |
| API di comando del bot Discord | `src/core/skills/voice/bot/api/server.js` |
| Ingestione voce Discord + VAD | `src/core/skills/voice/bot/classes/VoiceManager.js:122` |
| Protocollo mod Minecraft (lato Python) | `src/core/skills/minecraft/client.py:66` |
| Dispatch dei pacchetti dalla mod | `src/core/skills/minecraft/client.py:151` |
| Entrypoint mod + tick loop | `beacraft/…/BeaCraftMod.java:36` |
| Stato di gioco serializzato | `beacraft/…/GameStateGatherer.java:22` |
| Canale eventi mod → Python | `beacraft/…/ActionManager.java:170` (`broadcast`) |
| Azioni di gioco (skill Java) | `beacraft/…/skills/*.java` |
| Prompt | `data/prompts/{soul,operating,monologue,minecraft}.md` |

### 10.2 Contratto di una perception

```python
Perception(
    kind=PerceptionKind.CHAT,          # CHAT|VOICE|GAME|ACTION|IDLE|SYSTEM
    surface="discord:text",            # chi l'ha prodotta
    content="[marco] ciao bea",        # testo già renderizzato
    salience=0.8,                      # INFORMATIVO, non imperativo
    meta={"channel_id": "...", "message_id": "...", "conversation_key": "discord:123"},
    author=Author(platform="discord", native_id="4711", display_name="marco"),
)
```

Regola: `author.identity` (`platform:native_id`) è la verità, il `display_name`
è cosmetico. Ogni skill di input è responsabile di costruire un `Author`
corretto e stabile.

### 10.3 Contratto di un tool

```python
Tool(
    name="discord_reply",
    description="...",                 # è prompt: scriverla come si scrive un prompt
    parameters={...},                  # JSON Schema
    handler=async_or_sync_callable,    # ritorna una stringa = osservazione
    long_running=False,                # True → gira async, preempta, torna come perception
)
```

Gli errori **non** si sollevano: si ritornano come osservazione
(`tools.py:84-94`), così il modello può reagirci invece di far cadere il loop.

### 10.4 Comandi

```bash
make install        # uv sync
make run            # CLI
make web            # build frontend + dashboard su :8000
make test           # (dalla Fase 0)
make lint           # (dalla Fase 0)
```

Bot Discord: `cd src/core/skills/voice/bot && npm install` (una volta).
Mod Minecraft: build ed esecuzione dalla sua repo (vedi §4.7).
