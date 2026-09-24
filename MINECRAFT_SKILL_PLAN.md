# Minecraft skill — analysis, live test results, and implementation plan

> **Reader:** a Claude instance with **no context** from the session that produced this.
> You have access to three repositories (paths in §2). Everything you need is in this
> file: what exists, what was measured, what is broken, what to build, in what order,
> and how to test it. Nothing here is a guess: every claim is tagged with how it was
> verified — **[RUN]** reproduced in a live game, **[BYTECODE]** read from the
> decompiled Minecraft 26.2 client, **[CODE]** read in source (file + lines), or
> **[UNVERIFIED]** stated explicitly as not verified.
>
> This file is a working plan. It is **not** documentation and must **not** be committed
> (the owner keeps plans out of the repo). Do not copy its wording into `docs/`.

---

## 0. Riassunto per il proprietario (IT)

- Il corpo di Bea non è "scarso" per colpa del modello: la mod gli **mente**. In gioco ho
  misurato che `place_block` riporta `SUCCESS` anche quando non piazza nulla (fuori
  portata) o piazza nella coordinata sbagliata; `mine_block` lascia i drop a terra;
  `find_block` può andare in **loop infinito**; i risultati delle azioni vengono
  **attribuiti all'azione sbagliata** (AutoEat, autodifesa); la chat di Bea (`mc_chat`)
  **interrompe** ciò che il corpo sta facendo; il brain **scarta** il messaggio di ogni
  risultato (legge `message`, la mod manda `details.message`).
- Il mining si blocca in silenzio se la finestra di Minecraft perde il focus o ha una
  GUI aperta (verificato nel bytecode + A/B in gioco). Durante uno stream è la norma.
- Il corpo **non vede** alberi, pietra o minerali oltre 4 blocchi: il lidar nomina solo
  blocchi "interessanti" e i tronchi non ci sono.
- Costruire oggi = una `place_block` per blocco con coordinate esatte, senza camminare,
  senza verifica. Mindcraft invece ha primitive **complete** (cammina → seleziona →
  piazza su una faccia → verifica → spiega) e compone strutture con codice/blueprint.
- Ho prototipato e testato in gioco: protocollo v2 (id rimandato), mining via
  `gameMode`, `place_block` v2. Risultati A/B nel §6. Il piano (§10) è in fasi,
  ordinate per impatto, con codice, test e criteri di accettazione.
- Decisioni che servono da te prima di implementare: §12.

---

## 1. Ground rules for whoever implements this

These come from the owner's global instructions and project memory. Follow them exactly.

1. **Python:** always `uv` (`uv run`, `uv add`, `uvx`). Never `pip`, never bare `python3`.
2. **Comments:** only *why*, never *what*; one line max; **all lowercase**; no emojis; few
   of them. Match the density of the surrounding file. (projectBEA's existing code has
   longer explanatory docstrings — match the file you are in, but new inline comments
   follow the rule above.)
3. **Commits:** only when asked; after each completed phase; message 5–6 words, plain
   language, **no co-author, no signature, no mention of Claude**, written as if the
   owner typed it (`git add . && git commit -m "..."`).
4. **Never put the owner's name** ("ema") in branch names, tests, fixtures, commits or PRs.
   Use neutral names (e.g. `marco`) in tests.
5. **PRs (projectBEA):** fill `.github/PULL_REQUEST_TEMPLATE.md`; **no attribution line**
   of any kind in the body; before opening, run every CI step locally:
   `uv run ruff check src tests`, `uvx pyright` (src must be 0 errors — fix types
   properly, never `# type: ignore`), `uv run pytest -q`, `BEA_PERF=off uv run pytest -q`,
   and the frontend `npm test` if the frontend changed.
6. **Docs:** `docs/` describes how the system works **now**, present tense, never a
   changelog. History and measurements belong in the PR body.
7. **No guessing:** every change and every claim must rest on a measurement, code or a
   log. If you cannot verify, say so and do not build on it.
8. **BeaCraft versions:** only the newest Minecraft branch is maintained (`mc/26.2`
   today). `gradle.properties` is **CRLF** — edit it binary-safe (a `sed '...$'` silently
   matches nothing). Version format `X.Y.Z+<mc version>`, one changelog file per version
   in `changelogs/`. Release: `make build`, then `uv run python tools/publish.py --dry-run`,
   then without `--dry-run` (needs `MODRINTH_TOKEN` in `.env` and an authenticated `gh`).
9. **Do not use browser tools** without explicit permission from the owner each time.
10. **Never enable a skill on Bea's behalf**: skills are capability gates the UI owns.

---

## 2. The three repositories

| Repo | Where | Branch / commit analysed | Stack |
|---|---|---|---|
| projectBEA (the AI VTuber, "brain") | `/Users/ema/Projects/projectBEA` | `main` @ `ef631d9` | Python 3.12, uv, asyncio |
| BeaCraft (the Fabric client mod, "body") | `/Users/ema/Projects/beacraft` (private) | `mc/26.2` @ `d3b4e46`, mod `2.1.0+26.2` | Java 25, Fabric Loader 0.19.5, Fabric API 0.161.0+26.2, Minecraft **26.2**, Loom 1.17 |
| mindcraft (external reference) | https://github.com/mindcraft-bots/mindcraft | `main` @ `5f3acc87b479864124173de444f31fa5538f94a6` (2026-06-08) | Node.js, mineflayer 4.x |

All mindcraft links below are pinned to that commit:
`https://github.com/mindcraft-bots/mindcraft/blob/5f3acc87b479864124173de444f31fa5538f94a6/<path>#L<a>-L<b>`.
Mindcraft is MIT-licensed (Copyright (c) 2024 Kolby Nottingham) — porting its data
(e.g. blueprint JSON) is allowed with attribution.

BeaCraft branches: `mc/26.2` (maintained), `mc/26.1`, `main` (old 1.21.1 line), plus local
`fix/follower-1.2.1`, `fix/pathfinder-astar`. **Note:** Mojang's version manifest lists
**26.3** as the latest release today (`26.4-snapshot-1` too). Porting is out of scope
here — ask the owner (§12).

### 2.1 Build / run commands (all verified in this session)

BeaCraft (portable JDK, nothing global):
```bash
make setup      # downloads Temurin 25 into ./.jdk if missing (it was missing on this machine)
make test       # JUnit: PathfinderTest, ProgressWatchTest, PathFollowerTest, LookControllerTest — all passed
make build      # remapped jar in build/libs/
```
Run the client from source, joined straight to a server (used for all live tests):
```bash
JAVA_HOME=$PWD/.jdk/current ./gradlew runClient --console=plain \
  --args="--quickPlayMultiplayer 127.0.0.1:25565 --username Bea"
```
Put `run/options.txt` in place first so the test client does not pause or beep:
```
pauseOnLostFocus:false
soundCategory_master:0.0
renderDistance:6
simulationDistance:6
maxFps:30
onboardAccessibility:false
joinedFirstServer:true
tutorialStep:none
narrator:0
skipMultiplayerWarning:true
```
Config: `config/beacraft.json` (`host`, `port`, `baritoneMode`, `baritoneDebugRender`),
overridable with `-Dbeacraft.host` / `-Dbeacraft.port` (`BeaCraftConfig.java:93-94`).

projectBEA:
```bash
uv run pytest -q tests/test_minecraft_*.py     # 62 minecraft tests exist today
uv run python tools/mc_contract.py --mod ../beacraft   # regenerates tests/fixtures/minecraft_contract.json
```

---

## 3. Architecture — projectBEA's Minecraft skill (the brain)

Canonical doc: `docs/skills/minecraft.md`. Files: `src/core/skills/minecraft/`.

```
mind (personality, chat, voice) ── 7 tools ──> play_minecraft(goal, have), mc_chat, mc_stop,
   │                                            mc_goto_player, mc_follow_player,
   │                                            mc_look_at_player, mc_give_item
   ▼ set_goal()
GameAgent (the "body"): one endless loop, model pool "minecraft" (falls back to "mind")
   │   27 game tools + update_notebook + goal_done/goal_blocked
   ▼ MinecraftClient.execute(action, params) — websocket, awaits a completion
BeaCraft mod (ws://127.0.0.1:8080) — drives the real Minecraft client (Bea's POV is the stream)
```

Key facts with lines:

- **Surface** `surface.py` — `MinecraftSurface(Skill)`, `name="game:mc"`, `skill_name="minecraft"`.
  Starts client + registry + `GameAgent` in `start()` (`surface.py:70-97`). Perception loop
  (`:118-150`): state snapshots are noise; events become `GAME` perceptions. Mind tools
  (`:483-588`); reflex tools **borrow** the body (`body()` wrapper `:491-512`,
  `GameAgent.borrow/give_back` `agent.py:231-253`). `mc_chat` sends the mod action `chat`
  as *instant* (`surface.py:600-604`). `live_state()` shows the goal + rendered state (`:614-635`).
- **Body** `agent.py` — `GameAgent.run()` loop (`:163-191`); one round `_step()` (`:285-326`):
  every `REFRESH_EVERY=3` steps re-injects `render_state` + notebook (`:287-288`), calls the
  model with all tool schemas, dispatches every tool call sequentially, counts failures;
  `STEPS_PER_GOAL=40` (`:29`), `MAX_FAILURES=5` (`:36`), `TICK_SECONDS=0.4` (`:41`).
  A goal only ends via `goal_done` (checked against inventory if `have` was given,
  `:121-139`, `goal.py:64-80`) or `goal_blocked`. Milestones for a subset of tools
  (`_MILESTONE_TOOLS` `:417-420`). Failure detection is by prefix (`_went_wrong` `:425-426`:
  `FAILURE`, `FAILED`, `ERROR`, `TIMEOUT`, `INTERRUPTED`).
- **Context** `context.py` — window of `KEEP_ROUNDS=12` whole rounds; tagged notes replace
  each other (the state note).
- **Tools** `tools.py` — `_TOOLS` dict (`:33-196`) → `build_minecraft_tools()` (`:199-233`).
  `_INSTANT = {"request_screenshot", "check_death_log", "stop_moving", "chat"}` (`:19`):
  these return `"SENT"` without waiting (`client.py:105-107`).
- **Client** `client.py` — websocket on a thread, everything handed to the loop with
  `call_soon_threadsafe`. `execute()` (`:90-123`) sends `{"action","parameters","id"}`
  and awaits a future, `ACTION_TIMEOUT=60` (`:16`). `_handle()` (`:193-232`) dispatches on
  `type` (`chat`, `player_event`, `combat`, `death_event`), then `status`
  (`CONNECTED` handshake, `ENGAGED_AUTO_ACTION`, `INTERRUPTED`, `FINISHED/IDLE`).
  **Completion text = `result` + top-level `message`** (`:228-232`). Matching: by `id` if
  the packet has one, otherwise FIFO to the oldest waiter, skipping "abandoned" ids
  (`_settle` `:273-301`). Handshake: the client speaks protocol `1` (`PROTOCOL_VERSION`
  `:19`) and only **logs an error** on a mismatch or a missing protocol (`:234-262`); it
  still drives the jar.
- **State rendering** `state.py` — `render_state()` (`:19-49`): health/food/pos, inventory,
  armour, "can craft now" (from the mod's `craftable_2x2/3x3`), lidar (`:127-165`:
  notable blocks with coordinates, max 12, 3 per kind; bulk census; ground/ceiling),
  entities (8 nearest), open GUI.
- **Prompts** — mind: `data/prompts/minecraft.md` (3,633 chars); body:
  `data/prompts/minecraft_body.md` (4,994 chars: rounds, goal_done/blocked, notebook with
  crafting chain, survival guide, rules). Measured: body tool schemas = **8,760 chars**;
  a rendered state ≈ 336 chars (vs 3,349 raw JSON).
- **Contract test** — `tools/mc_contract.py` parses `ActionManager.java`'s
  `KNOWN_ACTIONS` and `switch (action)` cases, and each skill's `params.has/get("…")`;
  `tests/test_minecraft_contract.py` holds brain schemas against
  `tests/fixtures/minecraft_contract.json`. It covers **parameters only, not response
  shapes** — which is how the `details.message` bug (§7 H1) survived: the unit tests in
  `tests/test_minecraft_social.py:140-203` feed the client a top-level `"message"` the real
  mod never sends.
- **Config** (`config.example.json`): `server_url`, `idle_nudge_seconds` 90,
  `commentary_seconds` 20, `steps_per_goal` 40, `tick_seconds` 0.4,
  `body_context_rounds` 12, prompt paths. Models: `mind` = `openrouter:deepseek/deepseek-v4-flash`,
  `groq:openai/gpt-oss-120b`; `minecraft` empty → borrows `mind`.

---

## 4. Architecture — BeaCraft (the mod)

Client-side Fabric mod. It simulates input and calls `MultiPlayerGameMode` so a vanilla
server sees a normal client. All paths below are under
`src/main/java/com/example/beacraft/` on `mc/26.2`.

- **Entry** `BeaCraftMod.java` — starts the websocket server (`startWebSocketServer`
  `:125-144`, loopback by default), registers chat listener + `/beacraft` command, and
  per client tick (`onClientTick` `:43-94`) runs, in order: `SelfPreservationManager`,
  `ActionManager.tick`, `AutoEatManager`, `GravityDefyerManager`, `DeathManager`,
  `StuckManager`; every 20 ticks sends `GameStateGatherer.captureGamePacket` to all
  clients. Automation only runs while ≥1 websocket client is connected. Handshake
  (`:153-170`): `status:CONNECTED`, `protocol:1`, `mod_version`, `mc_version`, `planner`,
  `baritone_installed`, `actions`.
- **Transport** `SimpleWebSocketServer.java` — every message is executed on the client
  thread (`onMessage` `:42-50`). It **logs every received message at INFO**, including the
  `id` the brain sends — which the mod then ignores.
- **ActionManager.java** — one current `Skill` at a time. `KNOWN_ACTIONS` (`:26-31`, 25
  actions). `handleCommand` (`:70-209`): parses, rejects unknown actions, **calls `stop()`
  on whatever is running for every action including `chat`, `check_death_log`,
  `request_screenshot`** (`:96`), then instantiates the skill. `stop(silent)` (`:232-246`)
  broadcasts `{"status":"FINISHED","action":"unknown","result":"INTERRUPTED"}` unless
  silent (`:241`). `tick` (`:249-287`) broadcasts on finish
  `{"status":"FINISHED","result":…,"action":…,"details":<feedback JsonObject>}` —
  **the human-readable text is `details.message`, never top-level `message`** (`:270-275`).
  No request id anywhere. `startSkill()` (`:60-68`) is used by managers to start
  "programmatic_*" skills. Idle head animation when nothing runs (`handleIdle` `:301-375`).
- **Skills** (`skills/`, interface `Skill.java`: `start/tick/stop/isFinished/getFeedback/getResult`):

| Action | Skill | What it really does (key lines) |
|---|---|---|
| `move_to` | `MoveSkill` | plans with `Planners.forClient` (own A* or Baritone), follows nodes pressing keys; exact goal tile, arrival tolerance 1.5; replans ≤3 on partial paths; mining **allowed** during paths (`PathOptions(true,…)` `:187-188`); disables pillar/bridge when no blocks (`:84-95`). Feedback has a good `message` (`:589-613`). |
| `mine_block` | `MineSkill` | vein BFS for `_ore`/`_log` over a **9×9×9 neighbourhood per block, up to 200 blocks** (`:80-139`); navigates to one of 12 neighbour cells (`getBestStandingPosition` `:384-437`) with pillar/bridge **off** (`:284-285`); breaks by **holding the attack key** (`:378`); no retry cap; result is always `SUCCESS` unless args missing (`:454-456`). |
| `find_block` | `FindSkill` | shell scan up to radius 100 (40k blocks/tick) with `SmartBlockMatcher`; walks with `MoveSkill`, "arrived" if within **6 blocks** (`checkArrival` `:179-184`), then `MineSkill`; counts collected items via `InventoryTracker` (inventory delta); `foundAny=true` after any `MineSkill` finish even if 0 mined (`:157-170`). |
| `place_block` | `PlaceSkill` | selects the block **from the hotbar only** (`:88-102`); clicks the **top face of the target position itself** (`BlockHitResult(... Direction.UP, pos ...)` `:68-72`); no reach check, no walking, no verification — finishes `SUCCESS` right after sending (`:78`); feedback message always "Place action executed" (`:150`). |
| `craft_item` | `CraftingSkill` | recipes only from the client recipe book (= unlocked recipes); variant fallback by suffix; **uses a table only if one is within a 5-block cube and takes the first found in x/y/z loop order, not the nearest** (`findNearbyTable` `:310-323`); clicks it from where she stands (no walking, `:173-188`); 2x2 vs 3x3 decided by **ingredient count ≤4** (`:156`); verifies by inventory count; failure feedback has key `error`, no `message` (`:442-452`). `quantity` = number of crafts, not items. |
| `use_block` | `InteractBlockSkill` | looks at the block and `useItemOn(... UP ...)`; no walking, no reach check; waits 10 ticks; `SUCCESS`. |
| `smelt_item` | `SmeltSkill` | **requires the furnace GUI already open** (`:26-31`); moves input + fuel into slots; does not wait for smelting; `SUCCESS` "Smelting setup finished". |
| `store_item` / `retrieve_item` | `ContainerSkill` | requires a container GUI already open; quick-moves **every** stack whose id *contains* the query (`SmartBlockMatcher.countsAs` `:110`, `:127`). |
| `equip_item` | `EquipSkill` | finds first stack whose id *contains* the query; mainhand via hotbar select/swap; armour via quick-move; offhand swap with slot 45. |
| `discard_item` | `DiscardSkill` | throws stacks whose id *contains* the query (`:76`). |
| `eat_food` | `EatSkill` | best food by score, holds `keyUse` 35 ticks. |
| `attack_entity` | `AttackSkill` (795 lines) | target by player name, numeric id or entity type; armour/shield/weapon setup; straight-line approach (no pathfinding); crit timing; heal at ≤10 hp; **searches forever if the target is not found** (`:154-161`). |
| `pillar_up`, `mine_down`, `bridge` | `PillarSkill`, `MineDownSkill`, `BridgeSkill` | jump-place, dig-fall, sneak-backwards bridging. `BridgeSkill.FIND_EDGE` has **no timeout** (`:146-163`). |
| `goto_player` / `follow_player` | `FollowSkill` (`once` injected by ActionManager) | repaths when the target moves >3 blocks; arrives at 3 blocks. |
| `give_item` | `GiveSkill` | FollowSkill(once) then DiscardSkill. |
| `look_at`, `select_slot`, `chat` | `LookSkill`, `InventorySkill`, `ChatSkill` | trivial. |
| `check_death_log` | — | broadcasts `DeathManager.getLastDeathInfo()` = `{"error":…}` or `{"result":"death_log",…}` — **no `status`, no `type`** (`DeathManager.java:166-185`). |
| `request_screenshot` | — | broadcasts `{"type":"screenshot","data":<base64>}` (`ScreenshotUtils.java:32`). |

- **Managers** (passive, every tick):
  - `SelfPreservationManager` — on damage, guesses the attacker, broadcasts `type:combat`,
    and for monsters/players **silently stops** the current action (`ActionManager.stop(true)`)
    and starts `AttackSkill` programmatically (`triggerDefense` `:232-260`); a threat queue
    re-engages repeatedly (`processThreatQueue` `:203-230`).
  - `AutoEatManager` — whenever idle and **food < 20** (`:35`), starts `EatSkill` (`:41`),
    5 s cooldown (`:44`) — even with no food in the inventory.
  - `StuckManager` — for `move_to`/`find_block`: no 0.5-block progress in 10 s, or >4 yaw
    jumps >45° in 1 s → silent stop + `{"status":"INTERRUPTED","event":{"type":"stuck","reason":…}}`.
  - `DeathManager` — on death: `INTERRUPTED` "Death Detected", auto-respawn after 4 s, then
    `{"type":"death_event","status":"DIED","details":{cause,death_pos,dimension,lost_items}}`.
  - `GravityDefyerManager` — water-bucket clutch when falling >3 blocks.
- **Perception** `GameStateGatherer.java` — every second: player (name, uuid, health, food,
  saturation, pos, rotation), inventory (hotbar, main, armour, hands), crafting context
  (`craftable_2x2` always, `craftable_3x3` only while a crafting table GUI is open, from
  `RecipeCalculator`), **lidar radius 4** (9×9×9) naming only blocks whose id contains one
  of `INTERESTING` (`:241-245`: `_ore, chest, barrel, furnace, crafting, water, lava, bed,
  door, torch, spawner, portal, anvil, shulker, hopper, sign, ancient_debris, beacon,
  enchanting`) — **no logs, no stone types, no sand/gravel/clay, no crops**; the rest is a
  census; ground and ceiling. Entities within 20 blocks; players online; GUI state.
- **Pathfinding** `utils/` — `Pathfinder` A* over standing positions with WALK/JUMP/FALL/
  MINE/MINE_DOWN/PILLAR/BRIDGE edges, hazard penalties, octile heuristic ignoring Y,
  `DEFAULT_MAX_NODES=15000`, runs **synchronously on the client thread**
  (`LegacyPlanner.request`). `WorldOracle` interface → unit-tested with `FakeWorld`.
  Optional Baritone (`Planners`, `BaritonePlanner`: `FULL` = Baritone walks, `PLAN` =
  Baritone plans, BeaCraft walks). Baritone is compile-only (`libs/baritone-api-26.2.jar`).
  On this machine `~/Library/Application Support/minecraft/mods` is empty/absent and
  `config/beacraft.json` has only `host`/`port` → in practice BeaCraft's own A* is used
  **[CODE+FS]**; which jar the owner streams with is **[UNVERIFIED]**.

---

## 5. Architecture — mindcraft (the reference)

mindcraft runs one **mineflayer** bot per agent (a headless protocol client: no rendering,
no POV). Its competence comes from the *library*, not the model.

- **Agent loop** `src/agent/agent.js` — `handleMessage()` (`#L254-L382`): add message to
  history, prompt the model, if the reply contains `!command(...)` execute it, append the
  command output as a `system` message, loop until the model answers in prose or
  `max_commands`. Death → system message with position, saved as place
  `last_death_position` (`#L475-L487`). `idle` event → clear controls, stop pathfinder,
  unpause modes, resume a resumable action (`#L488-L497`). Update loop every 300 ms runs
  modes + self-prompter (`#L503-L524`).
- **Commands** `src/agent/commands/actions.js` (32 actions) and `queries.js` (≈12 queries).
  Every action is wrapped by `runAsAction` (`actions.js#L6-L26`) → `ActionManager.runAction`.
  Examples: `!collectBlocks(type,num)` 10-minute timeout (`#L256-L265`), `!craftRecipe`
  with the explicit doc "NOT the number of output items" (`#L266-L276`), `!smeltItem`,
  `!placeHere`, `!goToCoordinates(x,y,z,closeness)`, `!searchForBlock(type, range≥32)`,
  `!moveAway`, `!rememberHere`/`!goToRememberedPlace` (`#L160-L182`), `!digDown`,
  `!goToSurface`, `!useOn`, `!goal` (self-prompting), `!newAction(prompt)` (code-gen,
  disabled unless `allow_insecure_coding`).
- **ActionManager** `src/agent/action_manager.js` — one action at a time; a new action first
  interrupts the old one (`requestInterrupt`: stop digging, cancel collect, stop pathfinder,
  stop pvp); per-action timeout; returns `{success, message, interrupted, timedout}` where
  **`message` is the accumulated `bot.output` log of the whole action** (`_executeAction`
  `#L61-L150`, `getBotOutputSummary` `#L152-L166`, capped at 500 chars keeping head and tail).
  Fast-loop detection kills runaway resumes (`#L64-L81`).
- **Skill library** `src/agent/library/skills.js` (2,093 lines). Every skill calls
  `log(bot, "...")` (`#L10-L12`) with a precise sentence, so the model always learns *why*.
  Each primitive is **complete**:
  - `placeBlock` (`#L611-L789`): cheat mode → `/setblock` with orientation; otherwise find
    item (creative: spawn it); if target already correct → "already at"; if occupied by a
    non-empty block → **break it** (`#L706-L715`); pick a **real neighbour face** to build
    off (`#L716-L751`, prefers `placeOn` side) — **no air-placing**, fails with "nothing to
    place on"; if the bot stands in the target → **step away** (`#L753-L763`); if >4.5 away
    → **path to within 4** (`#L764-L770`); equip, look, `bot.placeBlock(buildOffBlock, faceVec)`.
  - `breakBlockAt` (`#L561-L608`): path within 4 (no place/towers), `equipForBlock`,
    `canHarvest` check with a clear failure ("Don't have right tools to break X").
  - `collectBlock` (`#L417-L529`): aliases (`iron`→`iron_ore`, `+deepslate_`, `dirt`→`grass_block`,
    `cobblestone`→`stone`), nearest **safe-to-break** block within 64, `equipForBlock`,
    `canHarvest`, then `bot.collectBlock.collect(block)` (mineflayer-collectblock: path, dig,
    **pick up the drop**) or manual dig + `pickupNearbyItems` for crops/torches (`#L499-L503`),
    `autoLight` torches; reports "Collected N X". It does **not** verify the inventory delta.
  - `pickupNearbyItems` (`#L531-L558`): walks to each item entity within 8.
  - `craftRecipe` (`#L36-L115`): 2x2 first; else nearest table within 16; if none and a
    table is in the inventory → **place it** at a free spot, craft, **pick it back up**
    (`#L56-L83`, `#L106-L108`); walks to the table if >4 away; crafts `min(num, limit)` and
    reports the limiting resource; auto-equips crafted armour.
  - `smeltItem` (`#L142-L273`): nearest furnace within 16 or place one; checks input
    conflict; **fuel math** (`getFuelSmeltOutput`); waits collecting output every 1 s, stops
    after 11 s without progress (`#L234-L249`); takes leftovers back; picks the furnace up.
  - `goToGoal` (`#L1070-L1113`): tries a **non-destructive** path first (can't break glass,
    `digCost=10`, `placeCost=2`), then destructive; a **door-opening interval** opens nearby
    doors/fence gates/trapdoors when stuck >1.2 s (`#L1116-L1179`).
  - `goToPosition(x,y,z,min_distance)` (`#L1181-L1235`): `GoalNear` semantics, reports
    "reached" or "unable, N blocks away", aborts if the path needs a block it can't harvest.
  - `moveAway`, `avoidEnemies`, `digDown` (stops at lava/water/drops, `#L1906-L1961`),
    `goToSurface`, `useToolOn`/`useToolOnBlock` (line-of-sight check `#L2057-L2077`),
    `tillAndSow`, `goToBed`, villager trading, `putInChest`/`takeFromChest` with exact names.
- **Modes (reflexes)** `src/agent/modes.js` — ordered list, each with `interrupts` and
  `paused` flags (`#L24-L304`): `self_preservation` (water/lava/fire/falling blocks,
  flee at low health), `unstuck` (20 s without moving → `moveAway(5)`), `cowardice`,
  `self_defense`, `hunting`, `item_collecting` (idle pickup after 2 s), `torch_placing`,
  `elbow_room`, `idle_staring`, `cheat`. `execute()` (`#L306-L330`): runs the reflex as an
  action and, if it interrupted something, **re-prompts the model**: "Your previous action
  'X' was interrupted by Y. Your behavior log: …". Behaviour log is also injected before
  the next user message (`agent.js#L301-L309`).
- **Prompt** `profiles/defaults/_default.json` + `src/models/prompter.js`
  (`replaceStrings` `#L137-L204`): every call gets `$STATS` (= `!stats` + `!entities` +
  `!nearbyBlocks`), `$INVENTORY` (incl. what is worn), `$COMMAND_DOCS`, `$EXAMPLES`
  (few-shot selected by similarity), `$MEMORY` (500-char rolling summary, `history.js#L33-L80`),
  `$SELF_PROMPT`. `!nearbyBlocks` lists every distinct block type within 8, blocks below/at
  legs/at head, first solid block above (`queries.js#L104-L131`). Queries on demand:
  `!craftable`, `!getCraftingPlan` (recursive plan with missing items and leftovers,
  `queries.js#L268-L306` → `mcdata.js#L464-L572`), `!searchWiki`.
- **Code-gen** `src/agent/coder.js` — `!newAction`: prompt with relevant skill docs
  (`skill_library.js`: embedding/word-overlap selection, `placeBlock`/`wait`/`breakBlockAt`
  always shown), extract a code block, lint (unknown `skills.*`/`world.*` functions and
  ESLint), run in an SES `Compartment` exposing only `skills`, `world`, `Vec3`, `log`
  (`#L159-L202`), inject `if(bot.interrupt_code) return;` after every statement, up to 5
  attempts feeding errors back (`#L31-L114`). This is how mindcraft **builds**: the
  model writes loops over `skills.placeBlock` (see the "build a dirt house" example in
  `_default.json` `coding_examples`).
- **Blueprints** — `src/agent/npc/construction/*.json` (`dirt_shelter`, `small_wood_house`,
  `small_stone_house`, `large_house`): `{name, offset, blocks[y][z][x]}` with **generic
  names** (`planks`, `log`, `door`, `bed`, `torch`, `air`, `""` = don't care), resolved to
  the wood/wool type the bot has (`npc/utils.js#L5-L70` `getTypeOfGeneric`), satisfaction
  check (`#L73-L84`), rotation (`#L121-L126`); `BuildGoal.executeNext` (`build_goal.js#L20-L78`)
  breaks wrong blocks, places missing ones, and returns the **missing materials**.
  `tasks/construction_tasks.js` has a `Blueprint` class that explains per-level diffs as
  "Place X at …/Remove the Y at …/Replace…" (`#L120-L209`).
- **Connection hardening** `src/utils/mcdata.js#L55-L133`: position packets throttled to
  50 ms (Paper kicks otherwise), `PartialReadError` swallowed, plugins: pathfinder, pvp,
  collectblock, auto-eat (`startAt: 14`, banned foods, `agent.js#L190-L195`), armor-manager.

---

## 6. What was built and measured in this session

### 6.1 Test rig (reproducible — full code in Appendix A)

- A **vanilla Minecraft 26.2 server** (Mojang jar from the version manifest), offline
  mode, flat world (`bedrock, 3 stone, 2 dirt, grass`; surface at y=-57), RCON on 25575,
  `spawn-protection=0`, gamerules (26.x names!) `advance_time=false`, `spawn_mobs=false`,
  `spawn_monsters=false`, `advance_weather=false`, `keep_inventory=true`.
  Note: in 26.x the old camelCase gamerules (`doDaylightCycle`, …) are rejected **[RUN]**;
  `/fill` is capped at 32,768 blocks per call **[RUN]** (clear in slabs).
- The **BeaCraft client from source** (`runClient` + `--quickPlayMultiplayer`), username `Bea`.
- A Python **harness** (`mod.py`) that talks to the mod's websocket exactly like the brain,
  records every packet, and an **RCON client** (`rcon.py`) to set up scenarios and to check
  the world server-side (`execute if block …`, `kill @e[type=item]` to count drops,
  `data get entity … Inventory`).
- Some scenarios were run through **projectBEA's real `MinecraftClient`** (imported from
  the repo) to show exactly which observation the body model would receive.
- A **Minecraft 26.1 server** + mindcraft's own `skills.js`/`world.js`/`mcdata.js` driven by
  a Node script with no LLM (mineflayer supports up to 26.1, not 26.2 **[CODE]**:
  `mineflayer/lib/version.js` testedVersions ends at `26.1`; minecraft-data has no 26.2).

### 6.2 Results — BeaCraft as it is today (`mc/26.2` @ `d3b4e46`)

| # | Scenario | Mod reported | World / truth | Tag |
|---|---|---|---|---|
| E1 | `place_block` 10 blocks away | `SUCCESS` "Place action executed" (0.05 s) | nothing placed | [RUN] |
| E2 | `place_block` 2 blocks away on ground | `SUCCESS` | placed | [RUN] |
| E3 | `place_block` on an occupied cell (grass at (0,-58,2)) | `SUCCESS` | target untouched, block placed **one above** (0,-57,2) | [RUN] |
| E4 | `place_block` floating, no neighbour, in reach | `SUCCESS` | placed (vanilla accepts "air-place"; anticheat servers typically don't — [UNVERIFIED]) | [RUN] |
| E5 | block only in main inventory | `FAILURE_BLOCK_NOT_FOUND`, message still "Place action executed" | not placed | [RUN] |
| E7 | `mine_block` stone 4 blocks away | `SUCCESS` "Mined: 1" (1.8 s) | **cobblestone left on the ground**, inventory unchanged | [RUN] |
| E8 | `mine_block` base of an oak (6-log trunk) 5 away | `SUCCESS` "Mined: 4" (9.5 s) | **2 logs left floating**; 4 logs in inventory | [RUN] |
| E9a | `find_block log count=5` with floating logs 4.5 blocks away (a half-cut tree) | no completion in 180 s | **livelock every tick**: find → move FAILED → "arrived" (<6 blocks) → MineSkill "no standing position, skipping" → `foundAny=true` → rescan same log | [RUN] |
| E9b | `find_block log count=5`, clean world, trees ~10–12 blocks | `INTERRUPTED` POSITION_STAGNATION after 20 s; 0 logs | path tried to mine a head-level **leaf** repeatedly without breaking it (see E-focus) | [RUN] |
| E10 | craft chain planks→table→sticks→wooden_pickaxe, no table placed | first three `SUCCESS` (5 logs→20 planks: `quantity` = crafts); pickaxe `FAILURE` "Crafting failed (Verified: 0 -> 0)" | correct refusal, useless reason, no auto-place of the table in the inventory | [RUN] |
| E10b | wooden_pickaxe, tables at (2,-57,0) **and** (-5,-57,-5) | `FAILURE` | fails because the far table is found first; succeeds once the far one is removed | [RUN] |
| E-slab | 3 oak_planks, no table | state advertises `oak_slab` in `craftable_2x2`; crafting it → `FAILURE` | slab is 3×1, cannot be made in 2×2 | [RUN] |
| E-focus | `mine_block` stone 2 blocks away, window unfocused | no completion in 20 s | stone intact | [RUN] |
| E-screen | `mine_block` with a crafting-table GUI open (after `use_block`) | no completion in 20 s | stone intact | [RUN] |
| E11 | idle while food 12/20 with bread | unsolicited `{"status":"FINISHED","action":"programmatic_EatSkill",…}` packets | (they resolve whatever the brain is waiting for — see E-race) | [RUN] |
| E12 | `move_to` 20 blocks, then `chat` after 1 s | `FINISHED INTERRUPTED` (action "unknown"), then chat `SUCCESS` | **Bea's own chat line stopped the walk** at x=3.5 | [RUN] |
| E13 | `check_death_log` | `{"error":"No death recorded yet."}` | packet has no `status`/`type` → the brain drops it; tool returns `"SENT"` | [RUN] |
| E14 | `mine_block` stone floating 6 blocks up | no completion; still `busy` after 70 s | **552 full A* searches of 15,000 nodes in ~70 s** on the client thread (MineSkill re-navigates forever) | [RUN] |
| E16 | `pillar_up` 3 with cobblestone | `SUCCESS` 1.2 s | y −57 → −54 | [RUN] |
| E17 | `bridge NORTH 5` on flat ground | no completion in 25 s, still busy | walked backwards 47 blocks looking for an edge | [RUN] |
| E18 | 5×3 wall 3 blocks away, 15 `place_block` bottom-up | 15× `SUCCESS` in 1.9 s | 15/15 correct (all air-placed) | [RUN] |
| E18b | same wall 12 blocks away | mixed `SUCCESS`/`INTERRUPTED` | **0/5 placed** | [RUN] |
| E-match | `discard_item("stone")` with stone_pickaxe, stone_sword, cobblestone, stone | `SUCCESS` "Dropped 17 stone" | **threw away the pickaxe and the sword too** | [RUN] |
| E-sight | oak tree 7 blocks away, iron_ore 12 away, table 3.6 away | rendered state shows only `crafting_table`; census within radius 4 | tree and ore **invisible** to the body | [RUN] |

Brain-side, with projectBEA's **real** `MinecraftClient` against the same mod:

| # | Scenario | Observation the body got | Truth | Tag |
|---|---|---|---|---|
| R-A | AutoEat eating when the body sends `move_to`, then `mine_block` | `move_to → 'INTERRUPTED'` after 0.00 s; `mine_block → 'INTERRUPTED'` after 0.03 s | move_to *started*; each call received the stop of the *previous* skill (off-by-one cascade); stone never mined | [RUN] |
| R-B | a zombie hits her during `move_to` (SelfPreservation silently takes over) | `move_to → 'SUCCESS'` after 4.5 s | she is at x=3.2 (target 18); the `SUCCESS` was the **AttackSkill**'s result | [RUN] |
| all | any completion | text is `result` only (`SUCCESS`, `FAILURE`, …) — never the mod's explanation | `details.message` is dropped by `client.py:230` | [RUN]+[CODE] |

**[BYTECODE]** Minecraft 26.2 `net.minecraft.client.Minecraft.handleKeybinds()` ends with
`continueAttack(gui.screen() == null && !bl && options.keyAttack.isDown() && mouseHandler.isMouseGrabbed())`
(javap offsets 690–733). A held attack key only breaks blocks while **no screen is open
and the mouse is grabbed** (window focused). BeaCraft's `MineSkill` relies on exactly that
key (`MineSkill.java:378`). Movement keys have no such condition (walking worked unfocused).

### 6.3 Results — prototypes (branch `exp/runtime-harness`, patches in Appendix B)

| Prototype | Test | Before | After | Tag |
|---|---|---|---|---|
| **Mining via `MultiPlayerGameMode.continueDestroyBlock`** + `stopDestroyBlock` on stop | E-focus / E-screen (GUI open) | never finishes (20 s) | `SUCCESS` in **1.2 s / 1.4 s**, block gone | [RUN] A/B |
| **Protocol v2**: mod echoes `id` on FINISHED/INTERRUPTED; stopping an agent request always reports it (even "silent" stops); brain ignores id-less completions when protocol ≥2 and reads `details.message` | R-A (AutoEat) | both calls `INTERRUPTED` instantly, stone not mined | `move_to → 'SUCCESS: Arrived at BlockPos{x=10, y=-57, z=0}.'` (2.55 s); `mine_block → 'SUCCESS: Mining sequence finished. Mined: 1'` (2.70 s); stone gone | [RUN] A/B |
| same | R-B (zombie) re-run | `'SUCCESS'` while 15 blocks short | self-defence interruptions now arrive as `INTERRUPTED` with the right id (seen in the log); a run where the zombie missed returned the true `SUCCESS: Arrived…` at x=18.4 | [RUN] |
| **PlaceSkill v2** (support face, whole-inventory selection by swap, reach check, body check, verification, reason codes) | E1 | `SUCCESS`, nothing placed | `FAILURE_OUT_OF_REACH` "(10, -57, 0) is 10,0 blocks away; get within 4 blocks first." | [RUN] |
| | E3 | `SUCCESS`, wrong cell | `FAILURE_OCCUPIED` "grass_block is in the way at (0, -58, 2); mine it first." (cell above untouched) | [RUN] |
| | E4 | `SUCCESS` (air-place) | `FAILURE_NO_SUPPORT` "nothing to place against…" | [RUN] |
| | E4b (own feet) | — | `FAILURE_BODY_IN_THE_WAY` | [RUN] |
| | E5 | `FAILURE_BLOCK_NOT_FOUND` | `SUCCESS` (swapped from main inventory) | [RUN] |
| | E18 wall | 15/15 (air-place) | **15/15 in 3 trials** (6.3–6.5 s each), every block against a real face | [RUN] |
| | E19 overhang off the wall top (side faces only) | — | 2/2 `SUCCESS` | [RUN] |

Bug found in the prototype itself: `String.format("%.1f")` printed `10,0` — the JVM
locale is Italian. **Always format with `Locale.ROOT`** in anything the model reads.

### 6.4 Results — mindcraft's library on Minecraft 26.1 (no LLM)

| # | Scenario | Returned | Truth (server-side) | Tag |
|---|---|---|---|---|
| M1 | `placeBlock` 10 blocks away | `true` 1.4 s, log "Found non-destructive path. \| Placed cobblestone at (10, -57, 0)." | placed | [RUN] |
| M2 | `placeBlock` on grass at (0,-58,2) | `true` 2.0 s, "grass_block in the way… Broke grass_block… Placed cobblestone at (0, -58, 2)." | placed at the exact cell | [RUN] |
| M2b | floating, no support | `false` "Cannot place cobblestone at (2, -54, -1): nothing to place on." | not placed (no air-place) | [RUN] |
| M3 | `collectBlock oak_log 5`, trees ~10 away | `true` 31–59 s, "Collected 5 oak_log." | 7 oak_log in inventory, **0 items left on ground** | [RUN] |
| M4 | `craftRecipe wooden_pickaxe`, table only in inventory | `true` 7.5 s, "Placed crafting_table … Successfully crafted wooden_pickaxe … Collected 1 crafting_table." | pickaxe + table back in inventory | [RUN] |
| M5 | `collectBlock stone 1` | `true` "Collected 1 stone." | no cobblestone in inventory (dirt instead) — **mindcraft over-reports too**: success = "collect() resolved", no inventory check (`skills.js#L505-L510`) | [RUN] |
| M6 | 5×3 wall 12 blocks away via a `placeBlock` loop | 15/15 `true`, 11 s | 15/15 placed | [RUN] |

Take-away: copy mindcraft's *completeness* (walk → prepare → act → verify → explain) and
its *explanations*, but verify outcomes against the world (inventory/block deltas) — which
BEA already does at goal level with `have` and which mindcraft does not.

---

## 7. Weak points (ranked). ID · impact · evidence · where · fix

### HIGH

- **H1 — The brain drops every explanation.** Completions carry the text in
  `details.message`; `client.py:228-232` reads top-level `message`. The body only ever sees
  `SUCCESS`/`FAILURE`/`INTERRUPTED`. [RUN]+[CODE] `ActionManager.java:270-275`.
  *Fix:* protocol v2 (§10 Phase 1): mod sends a top-level `message`; brain also reads
  `details.message`/`details.error` (prototype `_message_of`, Appendix B).
- **H2 — Results are attributed to the wrong request.** The mod never echoes `id`
  (`SimpleWebSocketServer` logs it, `ActionManager` ignores it); the brain falls back to
  FIFO; AutoEat, SelfPreservation's AttackSkill, `stop()` INTERRUPTED broadcasts and the
  mind's `chat` all emit completions nobody asked for. Measured: instant false
  `INTERRUPTED` cascades (R-A) and a false `SUCCESS` 15 blocks short (R-B). [RUN]
  *Fix:* protocol v2 id echo + id-only matching + autonomous actions reported as
  `type: reflex` events, never as completions (§10 Phase 1). Prototype validated.
- **H3 — Mining depends on window focus and on no GUI being open.** [BYTECODE]+[RUN] A/B.
  `MineSkill.java:378`. After `use_block` on a furnace + `smelt_item` (which never closes
  the GUI), every later `mine_block` hangs. *Fix:* `gameMode.continueDestroyBlock` each tick
  (prototype validated), `stopDestroyBlock` on stop; close stray GUIs before world actions.
- **H4 — `place_block` lies and is not usable for building.** No reach check/walking,
  hotbar-only, clicks the target's own top face (so an occupied target shifts the block up),
  no verification, constant message. [RUN] E1/E3/E5/E18b. `PlaceSkill.java:22-85`.
  *Fix:* PlaceSkill v2 (prototype validated) + walking into range + `build` (§10 Phase 3).
- **H5 — Livelocks and missing timeouts.** `FindSkill` loops every tick on unreachable
  blocks within 6 blocks (E9a, `FindSkill.java:130-170` + `MineSkill` skip path);
  `MineSkill` re-plans forever (E14: 552 A* × 15k nodes / 70 s); `BridgeSkill.FIND_EDGE`
  never ends on flat ground (E17); `AttackSkill` searches forever for an absent target
  (`:154-161`). The brain gives up at 60 s (`client.py:16`) while **the mod keeps going**
  and its eventual completion is then mis-delivered. [RUN]+[CODE]
  *Fix:* per-action watchdog in `ActionManager` + per-skill retry caps + unreachable
  marking (§10 Phase 2).
- **H6 — Drops are not collected.** Mining from reach distance leaves the item on the
  ground (E7: cobblestone left, inventory unchanged). `find_block`'s quota is an inventory
  delta, so it keeps looking for more blocks while the drops lie there. [RUN]
  *Fix:* pickup step after breaking (walk to `ItemEntity`s within 6–8 blocks), plus an idle
  item-collecting reflex (mindcraft `pickupNearbyItems` `skills.js#L531-L558`,
  mode `item_collecting` `modes.js#L188-L218`).
- **H7 — The body is blind beyond 4 blocks and to the most important resources.**
  Lidar radius 4 and an `INTERESTING` list without logs/stone/sand/gravel/clay/crops
  (`GameStateGatherer.java:241-247`). E-sight: a tree 7 blocks away and an ore 12 away do
  not exist for the model. [RUN]. *Fix:* resource scan radius 16–24 with nearest-per-kind
  (§10 Phase 4).
- **H8 — Building has no primitive.** One `place_block` per block with exact coordinates is
  the only way; no blueprint, no templates, no material planning, no progress. mindcraft
  builds via code-gen loops and blueprints (§5). *Fix:* `build` action (mod) + `plan_build`
  and `build_template` (brain) (§10 Phase 3).

### MEDIUM

- **M1 — `chat` (and every "instant" action) stops the running body action.**
  `handleCommand` calls `stop()` first (`ActionManager.java:96`). E12. The mind's `mc_chat`
  therefore interrupts the body mid-walk. *Fix:* concurrent actions bypass `stop()`.
- **M2 — Crafting helpers.** First-found table instead of nearest, no walking, no
  auto-place/pick-up of an inventory table, 2x2 decided by ingredient count (false
  `oak_slab` affordance), failure text without the missing ingredients, `quantity` =
  crafts not items (E10, E10b, E-slab). [RUN]
- **M3 — Loose item matching destroys equipment.** `SmartBlockMatcher.countsAs`
  (`:72-103`, substring at `:80`) used by discard/store/retrieve/equip/smelt:
  `discard_item("stone")` threw away a stone pickaxe and sword (E-match). [RUN]
  *Fix:* exact id match first; generic families only for explicit generic words
  (`log`, `planks`, `wool`, `ore`…) and never across item categories (tools/armour).
- **M4 — Smelting and containers need a GUI already open** and never close it; smelting
  does not wait for output. [CODE] `SmeltSkill.java:26-31, 162-165`,
  `ContainerSkill.java:49-54`. *Fix:* self-contained `smelt_item` like mindcraft
  (`skills.js#L142-L273`), `store/retrieve` that find, walk, open, move exact counts, close.
- **M5 — Destructive pathing.** Paths may MINE through anything breakable
  (`Pathfinder.java:192-198`, `MINE_SURCHARGE=2.0`). On a shared server this tunnels
  through players' walls. mindcraft tries a non-destructive path first
  (`skills.js#L1077-L1099`). [CODE] (not measured in-game). *Fix:* two-pass planning +
  protected block set.
- **M6 — AutoEat fires at food < 20, even with no food** (every 5 s:
  `FAILURE_NO_FOOD` spam in the log), and interrupts nothing but pollutes the protocol
  (E11). mindcraft eats at 14 (`agent.js#L191-L195`). [RUN]+[CODE]
- **M7 — Reflexes are invisible to the body.** SelfPreservation/Stuck/Gravity stop the
  action silently; the body never learns *why* (`reason` only on the `INTERRUPTED` packet
  from Stuck/Death). mindcraft re-prompts with a behaviour log (`modes.js#L306-L330`).
- **M8 — `check_death_log` and `request_screenshot` are dead tools.** Their replies have no
  `status`/`type` the brain dispatches on (E13; `ScreenshotUtils.java:32`). [RUN]+[CODE]
- **M9 — `MineSkill` vein BFS uses a 9×9×9 neighbourhood per block, up to 200 blocks**
  (`MineSkill.java:88-100`): one `mine_block` on a log can queue several trees; yet it
  still leaves unreachable top logs (E8). Replace with 26-neighbour connectivity + a cap
  + pillar/reposition for out-of-reach logs, and report what was left.
- **M10 — Tests describe the brain's assumptions, not the mod.** Response-shape fixtures
  don't exist; `test_minecraft_social.py` feeds a top-level `message`. *Fix:* recorded
  real packets as fixtures (§10 Phase 1).

### LOW

- **L1** `StuckManager` yaw-oscillation check ignores wrap-around (`:96-118`).
- **L2** Synchronous 15k-node A* on the client thread every replan (frame hitches).
- **L3** `InteractBlockSkill` never checks reach and always returns `SUCCESS`.
- **L4** `ContainerSkill` NPE path when `item` is missing (`countsAs(id, null)`), caught
  as `FAILURE_EXCEPTION` [CODE].
- **L5** Locale-dependent number formatting in messages (seen in the prototype).
- **L6** `AttackSkill` walks in a straight line (no pathfinding) and swings at up to 20 blocks.

---

## 8. Cross-analysis: ProjectBEA vs mindcraft

| Dimension | ProjectBEA + BeaCraft today | mindcraft | Gap (concrete) | Impact |
|---|---|---|---|---|
| Body substrate | real client via Fabric mod → **Bea's POV is the stream**; works on vanilla servers | headless mineflayer bot; POV only via prismarine-viewer | keep the mod — do **not** switch to mineflayer (loses the stream's POV) | — |
| Action feedback | `SUCCESS`/`FAILURE` only (H1) | full action log as text | port the log-everything pattern | HIGH |
| Request/response integrity | FIFO, broken by reflexes (H2) | one action at a time, in-process | id echo, reflexes as events | HIGH |
| Primitive completeness | place/craft/smelt/containers need the model to do navigation, GUIs, tables | primitives walk, prepare, act, clean up | make every primitive self-contained | HIGH |
| Verification | goal-level `have` check (good); action-level none | none (M5 over-reports) | verify world deltas per action **and** keep `have` | HIGH |
| Building | per-block `place_block` | code-gen loops + blueprint JSON + diff explanation | `build` (declarative), templates, `plan_build` | HIGH |
| Perception | pushed every second; radius 4, notable filter | `$STATS`/`$INVENTORY` every prompt; nearby types within 8; on-demand queries up to 512 | resource scan 16–24 + `scan` query | HIGH |
| Crafting knowledge | client recipe book (unlocked only), 2x2 by count | minecraft-data recipes; recursive `getCraftingPlan` | recipes extracted from the server jar + planner tool | MEDIUM |
| Reflexes | managers with hard-coded thresholds; silent | modes with priority, pause/unpause, behaviour log, re-prompt | reflex events + behaviour log + saner thresholds | MEDIUM |
| Pathing | own A* (unit-tested), optional Baritone; exact goal tile; destructive | mineflayer-pathfinder, `GoalNear`, non-destructive first, door opener | `range` goals, two-pass, protected blocks, doors | MEDIUM |
| Timeouts | brain 60 s; mod none | per action + unstuck + fast-loop kill | watchdog per action in the mod | HIGH |
| Memory | notebook (free text) + 12-round window | 500-char rolling summary + named places | named places (`remember_place`) + death place | LOW/MEDIUM |
| Prompting | good rules/notebook; no examples | few-shot examples selected by similarity | add 3–5 worked examples | LOW/MEDIUM |
| Safety of generated behaviour | tool calls only (safe) | `!newAction` runs model code (off by default: "insecure") | stay declarative; no code execution | — |
| Social layer | strong (identity, attention, two audiences) | basic chat | keep BEA's; nothing to port | — |

---

## 9. Reusable patterns (mindcraft → BEA mapping)

1. **Narrated actions** — every step appends a sentence to an action log
   (`skills.js#L10-L12`), returned capped (`action_manager.js#L152-L166`).
   → Java `ActionLog` in each skill; completion packet carries `message` + `log` (≤12 lines).
2. **Complete primitives** (`placeBlock`, `craftRecipe`, `smeltItem`, `collectBlock`):
   → PlaceSkill v2, CraftingSkill v2, SmeltSkill v2, CollectSkill (mine + pickup).
3. **Place against a face, never in the air** (`skills.js#L716-L751`) → PlaceSkill v2 (done).
4. **Clear the obstruction / step aside / walk in range** (`#L706-L770`) → PlaceSkill v2 + mover.
5. **Borrow and return infrastructure** (table/furnace placed then collected, `#L56-L108`, `#L159-L262`).
6. **Non-destructive first** (`#L1070-L1113`) + door interval (`#L1116-L1179`).
7. **GoalNear semantics** (`goToPosition(..., min_distance)` `#L1181-L1235`).
8. **Reflexes as a priority list with interrupt rules + behaviour log + re-prompt**
   (`modes.js#L24-L330`, `agent.js#L301-L309`).
9. **Per-action timeouts and loop kill-switch** (`action_manager.js#L64-L81`, `#L168-L175`).
10. **Stats/inventory in every prompt; queries on demand** (`prompter.js#L140-L149`,
    `queries.js`).
11. **Crafting plan** (`mcdata.js#L464-L572`) → Python planner over extracted recipes.
12. **Blueprints with generic materials + diff explanation** (`npc/construction/*.json`,
    `npc/utils.js`, `construction_tasks.js#L120-L209`).
13. **Named places / death place** (`actions.js#L160-L182`, `agent.js#L478-L479`).
14. **Aliases in resource names** (`collectBlock` `#L432-L440`: `iron`→`iron_ore`,
    `deepslate_`, `dirt`→`grass_block`, `cobblestone`→`stone`).
15. **Packet throttling for Paper** (`mcdata.js#L70-L98`) — not applicable (real client
    already rate-limits) → no action.

---

## 10. Implementation plan

Order is by impact and dependency. Each phase ends green (all tests, all CI steps) and is
committed separately (commit policy §1). Branches: projectBEA `feat/minecraft-body-v2`
(or one per phase), BeaCraft `feat/protocol-v2` etc. off `mc/26.2`. **Protocol changes
must ship in both repos together**; the brain must keep working (with an explicit error
log, not silently) against a protocol-1 jar until the owner updates the jar.

### Phase 0 — Live test harness (both repos) · enables everything else

Goal: anyone can reproduce §6 with two commands.

BeaCraft:
- Add `tools/live/` (Python, run with `uv run`):
  - `server.py` — downloads the vanilla server jar for `minecraft_version` from
    `gradle.properties` (Mojang manifest: `https://piston-meta.mojang.com/mc/game/version_manifest_v2.json`
    → version JSON → `downloads.server.url`), writes `eula.txt` and `server.properties`
    exactly as in Appendix A.1, runs it with the portable JDK (`.jdk/current/bin/java`).
  - `rcon.py`, `mod.py`, `world.py` from Appendix A (the harness).
  - `scenarios.py` — the §6.2 scenarios as functions returning pass/fail with the observed
    packet; `uv run python tools/live/scenarios.py --only place,mine` prints a table.
- Makefile targets: `live-server`, `live-client` (writes `run/options.txt` from A.2 and runs
  `runClient --args="--quickPlayMultiplayer 127.0.0.1:25565 --username Bea"`), `live-test`.
- Not in CI (needs a GPU window). Document in README "Development" section, present tense.

Acceptance: from a clean checkout, `make live-server` + `make live-client` +
`make live-test` reproduces the E-table.

### Phase 1 — Protocol v2 (both repos) · fixes H1, H2, M1, M7, M8, M10

**Wire format (mod → brain)** — every packet that answers a request:
```json
{"status": "FINISHED", "id": "r41", "action": "mine_block",
 "result": "SUCCESS" | "FAILURE_<CODE>" | "INTERRUPTED",
 "message": "one plain sentence, Locale.ROOT numbers",
 "log": ["walked 12 blocks to (4,-57,0)", "broke stone with wooden_pickaxe", "picked up 1 cobblestone"],
 "details": { ...skill-specific, unchanged keys kept for compatibility... },
 "reason": "self_defence: zombie"   // only for INTERRUPTED
}
```
- `id` is echoed on **every** reply to a request, including `INTERRUPTED` caused by a new
  command, a reflex, a stuck watchdog, death, disconnect.
- Autonomous behaviour never uses `status`. It is reported as
  `{"type":"reflex","reflex":"eat"|"defend"|"clutch"|"unstuck"|"respawn","event":"started"|"finished","message":"...","interrupted_id":"r41"|null}`.
- Queries answer like actions: `check_death_log` →
  `{"status":"FINISHED","id":…,"result":"SUCCESS","message":"you died at (…) to a zombie 3 min ago","details":{…}}`.
- **Concurrent actions** — `chat`, `check_death_log`, and later `scan` (Phase 4) — are
  executed **without** stopping the current skill and answered immediately with their own
  `id`. Whether `look_at`/`look_at_player` join this set is the owner's call (§12.8).
- `stop_moving` answers `{"result":"SUCCESS","message":"stopped mine_block"}` with its id and
  the stopped request gets its own `INTERRUPTED` with `reason:"stopped by request"`.
- Handshake: `"protocol": 2`, plus `"concurrent": ["chat","check_death_log"]`.

**BeaCraft changes**
- `ActionManager.java`: store `currentRequestId` (prototype in Appendix B.1); new
  `interrupt(String reason)` used by managers instead of `stop(true)`; `CONCURRENT` set
  handled before `stop()`; top-level `message` + `log` in every completion (take them from
  `Skill.getFeedback()` → add `default String message()` and `default List<String> log()` to
  `Skill`, or read `feedback.get("message")`); `Locale.ROOT` formatting.
- Managers: `SelfPreservationManager.triggerDefense` → `ActionManager.interrupt("self_defence: <mob>")`
  then start AttackSkill as an **autonomous** skill (`currentRequestId=null`), emit reflex
  events. Same for `StuckManager.triggerInterrupt` (`reason: "stuck: POSITION_STAGNATION"`),
  `DeathManager` (`reason: "death"`), `GravityDefyerManager` (`reason: "clutch"`),
  `AutoEatManager` (reflex only; never interrupts an agent request).
- `DeathManager.getLastDeathInfo` / `ScreenshotUtils` → answer with `status` + `id`.
- `BeaCraftMod.PROTOCOL_VERSION = 2`.

**projectBEA changes**
- `client.py`: `PROTOCOL_VERSION = 2`; store `self.protocol` from the handshake; when
  protocol ≥ 2: match **only by id**, drop id-less completions (debug log), route
  `type:"reflex"` to the surface via `on_event`; observation =
  `f"{result}: {message}"` + (`"\n" + "\n".join(log[-8:])` when present); keep FIFO only for
  protocol 1 and log an ERROR that the jar is outdated (prototype in Appendix B.2).
  Remove the `instant=True` "SENT" path for `chat`/`check_death_log`: they now get real
  answers (fast); keep `stop_moving` awaited too.
- `_TYPED_EVENTS` += `"reflex"`; surface `_on_mod_event("reflex")` → (a) append a line to
  a new `GameAgent.behaviour_log`; (b) for `defend`/`respawn`, emit a mind milestone.
- `GameAgent._step`: prefix the next model call with `"While you were working: <behaviour log>"`
  (mindcraft `agent.js#L301-L309`) and clear it.
- `tools.py`: per-action timeouts table (brain waits `mod_timeout + 5 s`, see Phase 2):
  `{"find_block": 240, "build": 900, "move_to": 120, "smelt_item": 180, default: 60}`.
- Tests (pytest, `tests/test_minecraft_protocol.py`, neutral names):
  - completion with `details.message` becomes `"SUCCESS: …"`;
  - protocol 2: an id-less `FINISHED` never resolves a waiter; an `INTERRUPTED` with id
    resolves exactly its caller; out-of-order ids resolve the right futures;
  - reflex packet reaches `on_event("reflex")`;
  - protocol 1 still resolves FIFO and logs the outdated-jar error.
  - **Recorded fixtures**: save real packets captured by the harness to
    `tests/fixtures/minecraft_packets/*.json` (handshake, game_state, finished, interrupted,
    reflex, death_event) and assert the client parses each. Update the existing tests in
    `test_minecraft_social.py:140-203` to the real shape.
- `tools/mc_contract.py`: still parses `case "…":` inside `switch (action)`; if concurrent
  actions are handled before the switch, keep them also listed in `KNOWN_ACTIONS` and make
  the parser read a `CONCURRENT_ACTIONS` set the same way (regex like `KNOWN`), otherwise the
  "declared but not wired" check fails. Regenerate the fixture; review the diff.

Acceptance (live, Phase 0 harness): R-A and R-B return the true results (see §6.3); E12:
`chat` no longer stops `move_to`; E13: `check_death_log` returns a readable sentence.

### Phase 2 — Mod reliability (BeaCraft) · fixes H3, H5, H6, M3, M6, M9

1. **Mining through the game mode** (prototype B.1 `MineSkill` hunk): replace
   `keyAttack.setDown(true)` with `if (gameMode.continueDestroyBlock(pos, face)) player.swing(MAIN_HAND)`;
   `stopDestroyBlock()` in `stop()`; pick `face` from the dominant axis toward the eyes.
   Before starting on a target: if `state.requiresCorrectToolForDrops()` and no inventory
   stack `isCorrectToolForDrops(state)` → `FAILURE_WRONG_TOOL` "iron_ore needs a stone
   pickaxe or better" (both methods exist in 26.2 **[BYTECODE]**). Close any open container
   screen before mining (`player.closeContainer()`).
2. **Watchdog**: `ActionManager` records `startedAt` and a per-action budget
   (`move_to` 90 s, `find_block` 180 s, `mine_block` 60 s, `build` 600 s, `craft_item` 30 s,
   `smelt_item` 150 s, default 45 s — always **less** than the brain's wait). On expiry:
   `interrupt("timeout: <what the skill was doing>")` → `FINISHED` `FAILURE_TIMEOUT` with id.
   Skills expose `String describeProgress()` for that message.
3. **MineSkill**: retry cap per target (2 navigation failures → skip with a logged reason);
   vein search with 26-neighbour connectivity (not a 9×9×9 box) capped at 64; if a vein
   block is out of reach and pillaring is possible (blocks in inventory) → pillar up under
   it; result `FAILURE_NOTHING_MINED` when `blocksMined == 0`; message lists what was left
   ("2 logs left out of reach at (5,-53,5), (5,-52,5)").
4. **Pickup**: new `PickupSkill` (walk to each `ItemEntity` within 6 blocks, nearest first,
   `MoveSkill` with range 0.8, 3 s budget per item, stop when none left or inventory full);
   called at the end of `MineSkill`/`FindSkill` and exposed as `pickup_items`. Report the
   inventory delta ("picked up 1 cobblestone").
5. **FindSkill**: arrival = within reach (4.5) of the block, not 6; a target whose
   `MineSkill` mined 0 blocks → add it (and its vein) to `unreachableBlocks`; `foundAny`
   only when the tracker's `collected > 0`; `getResult()` → `FAILURE_NONE_REACHABLE` /
   `SUCCESS`; default radius 48 (not 100) and prefer **exposed** blocks (≥1 air neighbour)
   before buried ones; message "collected 5/5 oak_log in 38 s; skipped 2 unreachable".
6. **BridgeSkill**: `FIND_EDGE` budget 60 ticks → `FAILURE_NO_EDGE` "not standing at an
   edge in that direction". **AttackSkill**: target lookup budget 100 ticks →
   `FAILURE_NOT_FOUND`; use the path mover when the target is >4 blocks away.
7. **Exact item matching** (`SmartBlockMatcher`): new `resolveItem(query, inventory)`:
   exact id (`minecraft:` optional) → registry alias table (`log`/`logs` → `#logs`,
   `planks` → `#planks`, `wool`, `stone` → `stone` **block only**, `cobble` → `cobblestone`) →
   no substring fallback for discard/store/equip. Tools and armour are only ever matched
   exactly. E-match must drop 5 stone only.
8. **AutoEat**: trigger at food ≤ 14 or health < 10 with food ≤ 19; only if edible food
   exists; only when no agent request is running; reflex events.
9. Every `String.format` → `String.format(Locale.ROOT, …)`.

Java unit tests (JUnit, no client): pure helpers extracted behind small interfaces like the
pathfinder's `WorldOracle`: vein connectivity, standing-position search, exposed-block
preference, item resolution (`resolveItem`), watchdog budget table.

Acceptance (live): E-focus/E-screen pass (≤2 s); E7 ends with the cobblestone in the
inventory; E9a returns `FAILURE_NONE_REACHABLE` in <10 s; E14 returns within its budget with
`FAILURE_UNREACHABLE`; E17 returns `FAILURE_NO_EDGE`; E-match drops only `stone`.

### Phase 3 — Building (both repos) · fixes H4, H8

**3a. PlaceSkill v2 (BeaCraft)** — start from the tested prototype (Appendix B.1, full
file) and add:
- walking: on `FAILURE_OUT_OF_REACH` inside the skill, pick a stand cell (standable, not the
  target, within 4.0 of the support face centre, reachable) and `MoveSkill` there with
  mining **off**, then retry once;
- `replace: true` parameter: break the occupying block first (via the Phase 2 miner);
- body in the way → step to an adjacent free cell (mindcraft `#L753-L763`);
- optional `facing` (north/south/east/west/up/down) for stairs/logs/doors: rotate the
  player to look in the opposite direction before `useItemOn` (vanilla derives facing from
  the player's horizontal direction) **[UNVERIFIED for each block type — test stairs,
  logs, doors, torches in the harness]**;
- air-place only if `allowAirPlace` in `config/beacraft.json` (default **false**, §12).
Result codes (tested): `SUCCESS`, `FAILURE_OUT_OF_REACH`, `FAILURE_OCCUPIED`,
`FAILURE_NO_SUPPORT`, `FAILURE_BODY_IN_THE_WAY`, `FAILURE_NO_ITEM`, `FAILURE_NOT_PLACED`.
Factor the core into `utils/Placer.java` (select → support → place → verify) so `build`
reuses it.

**3b. `build` action (BeaCraft `BuildSkill`)** — declarative, executed entirely in the mod.
Parameters (JSON, validated; unknown keys → `FAILURE_INVALID_ARGS` naming the key):
```json
{
  "origin": {"x": 10, "y": -57, "z": 4},
  "rotation": 0,                       // 0/90/180/270 around origin, clockwise seen from above
  "palette": {"#": "cobblestone", "P": "oak_planks", "D": "oak_door", "G": "glass_pane", ".": "air"},
  "layers": [                          // bottom layer first; each layer = rows along +z; chars along +x
    ["#####", "#...#", "#...#", "#####"],
    ["#####", "#...#", "#...#", "##D##"]
  ],
  "ops": [                             // optional, alternative or in addition to layers
    {"op": "fill", "from": [0,0,0], "to": [4,0,3], "block": "cobblestone", "hollow": false},
    {"op": "walls", "from": [0,1,0], "to": [4,3,3], "block": "oak_planks"},
    {"op": "set", "at": [2,1,0], "block": "air"},
    {"op": "roof", "from": [0,4,0], "to": [4,4,3], "block": "oak_slab"}
  ],
  "clear": true,                       // break blocks that don't match (default true for air cells, false for solid mismatches)
  "dry_run": false
}
```
Execution:
1. Expand to a map `cell → targetBlock` (relative → rotated → absolute). Cap 2,000 cells.
2. `dry_run` → report `{cells, already_ok, to_place:{item:n}, to_clear:n, missing:{item:n}}`
   using the whole inventory; no movement.
3. Order: clears top-down; placements by ascending y; within a y-level, cells that already
   have support first, then nearest-first from the current position (greedy); deferred
   cells are retried after each pass; after two passes without progress → mark
   `no support`.
4. Per cell: skip if satisfied (generic families: any `*_planks` satisfies `planks`, etc.,
   like mindcraft `npc/utils.js#L73-L84`); walk into range (stand cell not inside a future
   solid cell when possible); `Placer`; verify; one retry; record reason on failure.
5. Progress packet every 10 cells: `{"type":"progress","id":…,"done":n,"total":m,"message":…}`
   (brain uses it as the body's live "thought" and as commentary material).
6. Stop conditions: watchdog (600 s), missing material for every remaining cell, death,
   interrupt. Final message e.g. `"built 42/48 cells of the build; missing 4 oak_planks; 2
   cells had nothing to rest on: (12,-54,7), (13,-54,7)"`, `details` with the lists.
Java unit tests: expansion + rotation, ordering (supported first, bottom-up), satisfaction
rules, material counting — against a `FakeWorld`-style oracle.

**3c. Brain side (projectBEA)**
- Body tool `build(origin, rotation, palette, layers?, ops?, clear?)` (schema mirrors 3b;
  contract fixture regenerated).
- Brain-only tool `plan_build(...)` — same arguments; pure Python expansion + material
  count against `count_items(state)`; instant; answers "needs 60 cobblestone (you have 12),
  28 oak_planks (you have 0) …" so the model gathers first. Put the expansion in
  `src/core/skills/minecraft/blueprint.py` (pure, fully unit-tested) and make BuildSkill's
  Java expansion follow **the same** semantics (shared test vectors in
  `tests/fixtures/minecraft_blueprints/*.json`, checked by both pytest and JUnit).
- Templates: `data/minecraft/blueprints/*.json` — port mindcraft's `dirt_shelter`,
  `small_wood_house`, `small_stone_house` (MIT, attribution in the file header or a
  NOTICE — §12) in their native `{name, offset, blocks[y][z][x]}` format with generic names.
  Tools: `list_templates()` and `build_template(name, x, y, z, rotation=0)`; the brain
  resolves generic names from the inventory (Python port of `getTypeOfGeneric`,
  `npc/utils.js#L5-L70`) and sends a `build` with `layers` + `palette`.
- Body prompt: a short "BUILDING" section (plan_build → gather → build; read the report;
  fix only what failed) and one worked example.
- Mind prompt: nothing about coordinates; `play_minecraft("build a small wooden house next
  to the lake")` stays the mind's only interface.

Acceptance (live): the 5×3 wall 12 blocks away (E18b) → 15/15 with walking; a
`small_wood_house` template on flat ground with materials given via RCON → ≥95 % cells
correct (door/bed orientation reported separately), final report lists every miss.

### Phase 4 — Perception (both repos) · fixes H7

BeaCraft `GameStateGatherer`:
- `resources`: every 2 s (not every second — cost), scan a cube of radius 20 around the
  player with an **exposure** check, grouping by kind using tags:
  `logs (#logs)`, `leaves`, `stone`, `cobblestone`, `deepslate`, `coal_ore/iron_ore/copper_ore/
  gold_ore/redstone_ore/lapis_ore/diamond_ore/emerald_ore (+deepslate_)`, `sand`, `gravel`,
  `clay`, `water`, `lava`, `crafting_table`, `furnace`, `chest`, `bed`, mature `crops`.
  For each kind: `count`, nearest `{x,y,z,distance}`, nearest **exposed**. Budget the scan
  (≤ 70k `getBlockState` per packet; measure with the harness and log the ms).
- `world`: `time_of_day` (0–24000), `is_night`, `dimension`, `biome` at feet, `raining`,
  `thundering`, `light` at feet (mob danger), `game_mode`.
- Keep `lidar` (radius 4) for the fine-grained view.
projectBEA `state.py`: `- resources in sight: oak_log ×23 nearest (7,-57,0) 7m; iron_ore ×1
(12,-57,-3) 12m (exposed); water (…)` capped at 8 kinds, and `- time: night (hostiles
spawn)`. Tests in `tests/test_minecraft_state.py` style.
New body query `scan(kind, radius≤64)` → mod answers with the nearest N positions (instant,
concurrent-safe).

Acceptance (live): E-sight shows the tree and the ore with coordinates.

### Phase 5 — Crafting & smelting intelligence (both repos) · fixes M2, M4

- `tools/mc_recipes.py` (projectBEA): extract `data/minecraft/recipe/*.json` and
  `data/minecraft/tags/item/*.json` from the server jar of the current version (the 26.2
  server jar contains **1,586** recipe files — verified; format: `crafting_shaped` with
  `pattern` + `key`, `crafting_shapeless` with `ingredients`, `smelting` with `ingredient`,
  tags as `#minecraft:…`) into a compact `data/minecraft/recipes.json`
  (`{item: [{type, grid:"2x2"|"3x3", ingredients:{item_or_tag: n}, count}]}` + tags).
  Licensing/commit decision: §12.
- `src/core/skills/minecraft/crafting.py` (pure): recursive plan like
  `mcdata.getDetailedCraftingPlan` (`mcdata.js#L464-L572`) with leftovers, tags resolved
  against the inventory (any `#planks`), smelting steps (`furnace` + fuel), and "needs a
  crafting table" when any step is 3x3. Tool `crafting_plan(item, count)` (brain-only,
  instant). On every `craft_item` failure the brain appends the plan's first missing step
  to the observation.
- BeaCraft `CraftingSkill` v2: parameter `count` = **items wanted** (crafts =
  ceil(count / result count); keep `quantity` as legacy = crafts); nearest table within 16
  (sorted by distance), walk to it; if the recipe needs 3x3 (shape via
  `ShapedCraftingRecipeDisplay.width()/height()` — exists in 26.2 [BYTECODE]; shapeless:
  ingredient count) and no table: place one from the inventory with `Placer`, craft, pick
  it back up (config default true); failure message names the missing ingredients with
  counts. `RecipeCalculator` uses the same shape rule for `craftable_2x2`.
- `SmeltSkill` v2 (`smelt_item(item, count, fuel?)`): nearest furnace within 16 or place
  one; walk; open (Placer-style interaction); refuse if the input slot holds another item;
  fuel math from the game's fuel values; insert via quick-move/pickup clicks; loop:
  every 20 ticks take the output; stop at `count` or 220 ticks without progress; take
  back leftovers; close; pick the furnace up if placed. Message "smelted 5 raw_iron into 5
  iron_ingot using 1 coal".
- `store_item`/`retrieve_item` v2 (`item`, `count`): nearest chest/barrel within 32, walk,
  open, move exact counts with exact matching, close; `view_container` query.

### Phase 6 — Movement (BeaCraft) · fixes M5

- `move_to` gains `range` (default 1.0 for coordinates; skills pass 4.0 to reach blocks);
  `Pathfinder.findPath` takes a goal predicate (within range) instead of an exact tile.
- Two-pass planning: first `allowMining=false` with 5,000 nodes, then mining allowed;
  a protected set never broken by paths: glass/panes, doors, trapdoors, fence gates,
  beds, chests, barrels, furnaces, crafting tables, torches/lanterns, planks/stairs/slabs
  of any wood, wool, bricks, glass — configurable in `beacraft.json` (§12).
- Door handling: closed doors/fence gates are passable nodes with an `OPEN` step
  (`useItemOn` on the door when adjacent); plus a stuck-time door opener like mindcraft
  (`skills.js#L1130-L1176`).
- New actions: `move_away(distance)`, `go_to_surface()`.
- `StuckManager`: try `move_away(3)` once before interrupting (mindcraft `unstuck`
  `modes.js#L91-L139`).

### Phase 7 — Body loop, tools and prompts (projectBEA) · M7, low items

- Observations: `result: message` + last log lines (Phase 1) — already enough for the model
  to self-correct.
- Tool list for the body after all phases (names are the mod actions unless noted):
  `move_to(x,y,z,range)`, `move_away`, `go_to_surface`, `mine_block`, `find_block`
  (collects + picks up), `pickup_items`, `place_block(x,y,z,block,replace,facing)`,
  `build`, `build_template` (brain), `plan_build` (brain), `list_templates` (brain),
  `craft_item(item,count)`, `crafting_plan` (brain), `smelt_item(item,count,fuel)`,
  `store_item(item,count)`, `retrieve_item(item,count)`, `equip_item`, `discard_item(item,count)`,
  `eat_food`, `attack_entity`, `scan(kind,radius)`, `check_death_log`, `remember_place(name)`
  (brain, persisted per server address in the data dir), `go_to_place(name)` (brain →
  `move_to`), `look_at`, `use_block`, `pillar_up`, `mine_down`, `bridge`, `goto_player`,
  `follow_player`, `give_item`, `chat`, `stop_moving`, `update_notebook`, `goal_done`,
  `goal_blocked`. Remove `request_screenshot` from the body until vision exists (memory:
  nothing consumes an image), and `select_slot` (equip covers it).
- Descriptions: say what each tool does **and what it returns on failure**; `craft_item`
  count semantics; `find_block` "collects N items of this kind, picking up the drops".
- `data/prompts/minecraft_body.md`: add 3–5 compact worked examples (from nothing to a
  wooden pickaxe; from stone tools to iron; build a shelter with a template; reacting to
  `FAILURE_OUT_OF_REACH` and `FAILURE_NO_SUPPORT`); update the survival guide for the
  self-contained primitives (no more "use_block to open the table first").
- Death place: on `death_event`, `remember_place("last_death")` automatically (mindcraft
  `agent.js#L478-L479`).
- Update `docs/skills/minecraft.md` (present tense) and `docs/skills/overview.md` tool tables.

### Phase 8 — Optional: Baritone fast paths · [UNVERIFIED at runtime]

When Baritone is installed (`Planners.baritoneActive()`), `find_block` could delegate to
Baritone's mine process and `build` to its builder process (the Baritone API exposes
processes for mining and schematic building). Not tested in this session; the owner's
install shows no Baritone. Only consider after Phases 1–7, behind the existing
`baritoneMode` switch, and verify every call against `libs/baritone-api-26.2.jar` first.

### Release checklist (per phase that touches the mod)

1. BeaCraft: bump `mod_version` in `gradle.properties` (**CRLF**, binary-safe edit) —
   protocol change ⇒ minor bump (`2.2.0+26.2`); add `changelogs/2.2.0+26.2.md`;
   `make test`; `make build`; live scenarios green; `uv run python tools/publish.py --dry-run`,
   then publish (only after the owner says so).
2. projectBEA: regenerate the contract fixture; full CI steps (§1.5); PR with template, no
   attribution; docs present tense.

---

## 11. Test strategy summary

| Layer | What | Where | Runs in CI |
|---|---|---|---|
| Brain unit | protocol v2 parsing/matching, recorded real packets, render_state resources, blueprint expansion, crafting planner, tool schemas vs contract | `tests/test_minecraft_*.py`, `tests/fixtures/minecraft_*` | yes |
| Mod unit | pathfinder (exists), vein/standing search, item resolution, blueprint expansion/order, watchdog table | `src/test/java/...` with `FakeWorld` | `make test` |
| Contract | parameters (exists) + response shapes (new, from recorded packets) | both | yes |
| Live | §6 scenarios (+ new: build template, smelt, store, doors, non-destructive paths) | `beacraft/tools/live/` | no (manual, GUI) |
| End-to-end with a model | body plays a scripted goal ("get a stone pickaxe", "build the small_wood_house") on the flat test world; success checked with RCON (`data get entity Bea Inventory`, `execute if block`) | a small runner that starts `GameAgent` with a real model pool | no — costs API calls; **ask the owner before running** (never run with their keys unasked) |

---

## 12. Decisions the owner must make before implementation (ask, don't assume)

1. **Air-placing**: vanilla accepts it (E4); anticheat servers usually reject/flag it
   [UNVERIFIED]. Default off (proposed) or on?
2. **Recipes data**: extract Mojang's recipe/tag JSON from the server jar and commit a
   derived `recipes.json` (as minecraft-data does), or generate it at install/first run?
3. **Protected blocks for pathing**: which blocks may Bea never break while walking?
   (proposal in Phase 6). Should she ever break player-built blocks?
4. **Reflex authority**: may AutoEat/self-defence interrupt an agent action? Thresholds
   (proposal: eat at ≤14; defend always; flee at <6 hp without a weapon).
5. **Minecraft 26.3** is released; policy says only the newest version is supported —
   port BeaCraft to 26.3 before or after this work?
6. **Porting mindcraft blueprints** (MIT, with attribution) vs writing new templates.
7. **Code generation** (mindcraft's `!newAction`): this plan deliberately uses declarative
   `build` instead of running model-written code. Confirm.
8. **Concurrent actions**: only `chat` + queries, or also `look_at`/`look_at_player`
   (so the mind's reflex "look at who spoke" doesn't interrupt the body)?

---

## 13. Not verified / limitations

- Behaviour with **Baritone** installed (`FULL`/`PLAN`) was not run.
- Behaviour on **Paper/Spigot + anticheat** was not run (air-place, fast clicks, LOS).
- The **body LLM** was not run end-to-end (no model calls were made; no API keys used).
- `facing`/orientation for stairs, doors, beds, logs is designed but untested.
- E9b's leaf-mining stall on the original build happened while the window was unfocused;
  whether leaves specifically fail with the key-based miner was not isolated (the
  game-mode miner removes the dependency either way).
- The 2 s mining stall seen once in R-A (v1, after navigation) was not reproduced or
  explained.
- mindcraft numbers are on 26.1 (mineflayer does not support 26.2).

---

## Appendix A — Live harness (copy into `beacraft/tools/live/`)

### A.1 `server.properties` (plus `eula.txt` with `eula=true`)
```properties
online-mode=false
server-port=25565
server-ip=127.0.0.1
level-type=minecraft\:flat
spawn-protection=0
difficulty=easy
gamemode=survival
spawn-monsters=false
generate-structures=false
max-players=4
view-distance=8
simulation-distance=8
enforce-secure-profile=false
motd=bea-test
generator-settings={"layers"\:[{"block"\:"minecraft\:bedrock","height"\:1},{"block"\:"minecraft\:stone","height"\:3},{"block"\:"minecraft\:dirt","height"\:2},{"block"\:"minecraft\:grass_block","height"\:1}],"biome"\:"minecraft\:plains"}
enable-rcon=true
rcon.port=25575
rcon.password=beatest
```
Without `generator-settings` the 26.2 server fails to create a flat world
("No key layers in MapLike[{}]") **[RUN]**. After start, via RCON:
`gamerule advance_time false`, `gamerule spawn_mobs false`, `gamerule spawn_monsters false`,
`gamerule advance_weather false`, `gamerule keep_inventory true`, `time set day`,
`setworldspawn 0 -57 0`.
Run: `.jdk/current/bin/java -Xmx2G -jar server.jar nogui < /dev/null > server.log 2>&1`
(stdin from `/dev/null` is fine; use RCON for commands).

### A.2 `run/options.txt` — see §2.1.

### A.3 `rcon.py`
```python
"""minimal source rcon client for the local test server."""

import socket
import struct
import sys


class Rcon:
    def __init__(self, host="127.0.0.1", port=25575, password="beatest"):
        self.sock = socket.create_connection((host, port), timeout=10)
        self._id = 0
        self._send(3, password)
        self._recv()

    def _send(self, kind, body):
        self._id += 1
        data = struct.pack("<ii", self._id, kind) + body.encode("utf-8") + b"\x00\x00"
        self.sock.sendall(struct.pack("<i", len(data)) + data)

    def _recv(self):
        size = struct.unpack("<i", self._read(4))[0]
        data = self._read(size)
        return data[8:-2].decode("utf-8", "replace")

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("rcon closed")
            buf += chunk
        return buf

    def cmd(self, command):
        self._send(2, command)
        return self._recv()


if __name__ == "__main__":
    r = Rcon()
    for c in sys.argv[1:]:
        print(f"> {c}\n{r.cmd(c)}")
```

### A.4 `world.py`
```python
from rcon import Rcon
r = Rcon()
def clear_area(r=r, half=24, top=-30):
    # fill is capped at 32768 blocks per call, so clear in slabs
    out = []
    for y in range(-57, top + 1, 4):
        out.append(r.cmd(f"fill -{half} {y} -{half} {half} {min(y+3, top)} {half} air"))
    return out
def reset(r=r):
    r.cmd("kill @e[type=item]")
    res = clear_area(r)
    r.cmd("tp Bea 0 -57 0 0 0")
    r.cmd("clear Bea")
    r.cmd("effect clear Bea")
    return res
```

### A.5 `mod.py` (run with `uv run --no-project --with websocket-client python …`)
```python
"""drives the beacraft mod over its websocket and records every packet."""

import json
import threading
import time

import websocket


class Mod:
    def __init__(self, url="ws://127.0.0.1:8080", log_path=None):
        self.packets = []  # (t, dict) for every non-state packet
        self.state = {}
        self.handshake = None
        self._lock = threading.Lock()
        self._log = open(log_path, "a") if log_path else None
        self.ws = websocket.WebSocket()
        self.ws.connect(url, timeout=10)
        self.ws.settimeout(None)
        self._t = threading.Thread(target=self._reader, daemon=True)
        self._t.start()
        deadline = time.time() + 15
        while (not self.state or self.handshake is None) and time.time() < deadline:
            time.sleep(0.1)

    def _reader(self):
        while True:
            try:
                raw = self.ws.recv()
            except Exception:
                return
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            now = time.time()
            with self._lock:
                if data.get("status") == "CONNECTED":
                    self.handshake = data
                if data.get("type") == "game_state":
                    self.state = data
                    continue
                self.packets.append((now, data))
            if self._log:
                self._log.write(json.dumps({"t": now, "in": data}) + "\n")
                self._log.flush()

    def send(self, action, **params):
        self._n = getattr(self, "_n", 0) + 1
        self.last_id = f"h{self._n}"
        payload = {"action": action, "parameters": params, "id": self.last_id}
        if self._log:
            self._log.write(json.dumps({"t": time.time(), "out": payload}) + "\n")
            self._log.flush()
        self.ws.send(json.dumps(payload))
        return time.time()

    def since(self, t0):
        with self._lock:
            return [p for (t, p) in self.packets if t >= t0]

    def echoes_ids(self):
        return int((self.handshake or {}).get("protocol", 1)) >= 2

    def wait_finished(self, t0, timeout=60.0, rid=None):
        """first FINISHED/IDLE/INTERRUPTED packet after t0 (for request rid when the mod echoes ids)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for p in self.since(t0):
                if p.get("status") in ("FINISHED", "IDLE", "INTERRUPTED"):
                    if rid is None or not self.echoes_ids() or p.get("id") == rid:
                        return p
            time.sleep(0.05)
        return None

    def run(self, action, timeout=60.0, **params):
        t0 = self.send(action, **params)
        p = self.wait_finished(t0, timeout, rid=self.last_id)
        return p, time.time() - t0

    def inv(self):
        counts = {}
        inv = self.state.get("inventory") or {}
        for slot in (inv.get("hotbar") or []) + (inv.get("main") or []):
            name = str(slot.get("item", "")).split(":")[-1]
            if name and name != "air":
                counts[name] = counts.get(name, 0) + int(slot.get("count", 0))
        return counts

    def pos(self):
        p = (self.state.get("player") or {}).get("position") or {}
        return (p.get("x"), p.get("y"), p.get("z"))

    def fresh_state(self, wait=1.3):
        """the mod sends a state packet every 20 ticks; wait for the next one."""
        ts = self.state.get("timestamp")
        deadline = time.time() + 5
        time.sleep(wait)
        while self.state.get("timestamp") == ts and time.time() < deadline:
            time.sleep(0.1)
        return self.state
```
Lesson learned: a harness that matches replies by order reproduces the very bug it tests
(the first v2 wall run showed false `INTERRUPTED`s from AutoEat) — match by id.

### A.6 Representative scenario (placement)
```python
import json, time
from mod import Mod
from world import r, reset
m = Mod(log_path="e_place.jsonl")
def isb(x, y, z, b="cobblestone"):
    return "passed" in r.cmd(f"execute if block {x} {y} {z} {b}")
reset(); r.cmd("give Bea cobblestone 64"); m.fresh_state()
for label, (x, y, z) in {"far": (10, -57, 0), "near": (2, -57, 0), "occupied": (0, -58, 2),
                         "floating": (2, -54, -1)}.items():
    p, dt = m.run("place_block", x=x, y=y, z=z, block="cobblestone")
    msg = (p or {}).get("message") or (p or {}).get("details", {}).get("message")
    print(label, p and p.get("result"), msg, "| world:", isb(x, y, z))
```

### A.7 Brain-side scenario (uses projectBEA's real client)
```python
import asyncio, sys, time
sys.path.insert(0, "/path/to/projectBEA")      # the checkout under test
from src.core.skills.minecraft.client import MinecraftClient
from world import r, reset

async def main():
    c = MinecraftClient("ws://127.0.0.1:8080", asyncio.get_running_loop())
    c.connect(); await c.wait_until_ready()
    reset(); r.cmd("give Bea iron_sword"); r.cmd("kill @e[type=zombie]")
    task = asyncio.create_task(c.execute("move_to", {"x": 18, "y": -57, "z": 0}))
    await asyncio.sleep(0.4); r.cmd("summon zombie 1 -57 1")
    obs = await task; await asyncio.sleep(1.2)
    print(repr(obs), "at x =", round(c.latest_state["player"]["position"]["x"], 1))
    c.stop()
asyncio.run(main())
```
Run from the projectBEA checkout so its venv is used: `uv run python path/to/script.py`.
**Write outputs to an absolute scratch path**, never into the repo root.

---

## Appendix B — Prototype patches (tested, see §6.3)

### B.1 BeaCraft (`mc/26.2` @ `d3b4e46`)

`ActionManager.java` — request id echo and loud interrupts:
```diff
@@ public class ActionManager {
     private static Skill currentSkill = null;
     private static String currentActionName = "idle";
+    // the agent's request id, echoed on every answer so it never matches by order
+    private static String currentRequestId = null;
+
+    public static String getCurrentRequestId() {
+        return currentRequestId;
+    }
@@ public static void startSkill(Skill newSkill, JsonObject params) {
             currentSkill = newSkill;
             currentActionName = "programmatic_" + newSkill.getClass().getSimpleName();
+            currentRequestId = null;
             currentSkill.start(params, Minecraft.getInstance());
@@ public static void handleCommand(String message) {
             String action = json.get("action").getAsString();
+            String requestId = json.has("id") ? json.get("id").getAsString() : null;
@@
             if (newSkill != null) {
                 currentSkill = newSkill;
                 currentActionName = action;
+                currentRequestId = requestId;
                 currentSkill.start(params, Minecraft.getInstance());
@@ public static void stop(boolean silent) {
             currentSkill.stop(Minecraft.getInstance());
-            if (server != null && !silent) {
-                server.broadcast("{\"status\": \"FINISHED\", \"action\": \"unknown\", \"result\": \"INTERRUPTED\"}");
+            // an agent request is always told it ended, even by a "silent" stop
+            if (server != null && (!silent || currentRequestId != null)) {
+                JsonObject interrupted = new JsonObject();
+                interrupted.addProperty("status", "FINISHED");
+                interrupted.addProperty("action", currentActionName);
+                interrupted.addProperty("result", "INTERRUPTED");
+                if (currentRequestId != null) {
+                    interrupted.addProperty("id", currentRequestId);
+                }
+                server.broadcast(gson.toJson(interrupted));
             }
             currentSkill = null;
         }
         currentActionName = "idle";
+        currentRequestId = null;
@@ public static void tick(Minecraft client) {
                     result.addProperty("action", currentActionName);
+                    if (currentRequestId != null) {
+                        result.addProperty("id", currentRequestId);
+                    }
@@
                 currentSkill = null;
                 currentActionName = "idle";
+                currentRequestId = null;
```
(The production version adds `reason`, top-level `message`/`log`, reflex events and
concurrent actions — Phase 1.)

`BeaCraftMod.java`: `PROTOCOL_VERSION = 2;`

`MineSkill.java` — break through the game mode:
```diff
@@ public void stop(Minecraft client) {
             moveSkill = null;
         }
+        if (client.gameMode != null) {
+            client.gameMode.stopDestroyBlock();
+        }
         if (client.options != null) {
             client.options.keyAttack.setDown(false);
@@ public void tick(Minecraft client) {   // end of the MINING section
-        client.options.keyAttack.setDown(true);
-
-        // Note: We don't check for break completion here explicitly because the top
-        // check handles it
+        // break through the game mode, not the attack key: vanilla only honours a held
+        // attack key while the window has the mouse grabbed and no screen is open
+        Direction face;
+        if (ax > ay && ax > az) {
+            face = vecX > 0 ? Direction.EAST : Direction.WEST;
+        } else if (ay > ax && ay > az) {
+            face = vecY > 0 ? Direction.UP : Direction.DOWN;
+        } else {
+            face = vecZ > 0 ? Direction.SOUTH : Direction.NORTH;
+        }
+        if (client.gameMode.continueDestroyBlock(currentTarget, face)) {
+            client.player.swing(net.minecraft.world.InteractionHand.MAIN_HAND);
+        }
     }
```
(`ax/ay/az`, `vecX/vecY/vecZ` are the existing locals computed earlier in `tick`.)

`PlaceSkill.java` — full replacement (prototype; fix `String.format` to `Locale.ROOT`):
```java
package com.example.beacraft.skills;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class PlaceSkill implements Skill {
    private static final Logger LOGGER = LoggerFactory.getLogger("beacraft-skill-place");

    // the order a player reaches for: the floor first, then the walls, the ceiling last
    private static final Direction[] SUPPORT_ORDER = {
            Direction.DOWN, Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST, Direction.UP };

    private static final int VERIFY_TICKS = 4;

    private enum State { SELECT, PLACE, VERIFY, FINISHED }

    private State state = State.SELECT;
    private BlockPos pos;
    private String blockName;
    private BlockPos support;
    private Direction face;
    private int timer;
    private String result = "SUCCESS";
    private String message = "";

    @Override
    public void start(JsonObject params, Minecraft client) {
        if (!params.has("x") || !params.has("y") || !params.has("z")) {
            fail("FAILURE_MISSING_ARGS", "place_block needs x, y and z.");
            return;
        }
        pos = new BlockPos((int) Math.floor(params.get("x").getAsDouble()),
                (int) Math.floor(params.get("y").getAsDouble()),
                (int) Math.floor(params.get("z").getAsDouble()));
        blockName = params.has("block") ? params.get("block").getAsString().toLowerCase().replace(" ", "_") : null;
        state = State.SELECT;
    }

    @Override
    public void tick(Minecraft client) {
        if (state == State.FINISHED || client.player == null || client.level == null)
            return;
        if (timer > 0) {
            timer--;
            return;
        }
        switch (state) {
            case SELECT -> select(client);
            case PLACE -> place(client);
            case VERIFY -> verify(client);
            default -> { }
        }
    }

    private void select(Minecraft client) {
        BlockState there = client.level.getBlockState(pos);
        if (blockName != null && idOf(there).equals(blockName)) {
            finish("SUCCESS", blockName + " was already at " + fmt(pos) + ".");
            return;
        }
        if (!there.canBeReplaced()) {
            fail("FAILURE_OCCUPIED", idOf(there) + " is in the way at " + fmt(pos) + "; mine it first.");
            return;
        }
        if (bodyInTheWay(client)) {
            fail("FAILURE_BODY_IN_THE_WAY", "you are standing where the block would go; step aside.");
            return;
        }

        support = null;
        for (Direction d : SUPPORT_ORDER) {
            BlockPos n = pos.relative(d);
            BlockState ns = client.level.getBlockState(n);
            if (!ns.canBeReplaced() && !ns.getCollisionShape(client.level, n).isEmpty()) {
                support = n;
                face = d.getOpposite();
                break;
            }
        }
        if (support == null) {
            fail("FAILURE_NO_SUPPORT", "nothing to place against at " + fmt(pos) + "; build up from a solid block.");
            return;
        }
        if (!client.player.isWithinBlockInteractionRange(support, 0.0)) {
            double d = Math.sqrt(client.player.distanceToSqr(Vec3.atCenterOf(pos)));
            fail("FAILURE_OUT_OF_REACH", String.format("%s is %.1f blocks away; get within 4 blocks first.", fmt(pos), d));
            return;
        }

        int slot = findItem(client);
        if (slot < 0) {
            fail("FAILURE_NO_ITEM", blockName != null ? "you have no " + blockName + "." : "you have no blocks to place.");
            return;
        }
        int selected = client.player.getInventory().getSelectedSlot();
        if (slot < 9) {
            client.player.getInventory().setSelectedSlot(slot);
        } else {
            // main inventory: swap it into the hand's hotbar slot, as the number keys do
            client.gameMode.handleContainerInput(client.player.inventoryMenu.containerId, slot, selected,
                    ContainerInput.SWAP, client.player);
            timer = 2;
        }
        state = State.PLACE;
    }

    private void place(Minecraft client) {
        Vec3 hit = Vec3.atCenterOf(support).add(face.getStepX() * 0.5, face.getStepY() * 0.5, face.getStepZ() * 0.5);
        client.player.lookAt(net.minecraft.commands.arguments.EntityAnchorArgument.Anchor.EYES, hit);
        client.gameMode.useItemOn(client.player, InteractionHand.MAIN_HAND, new BlockHitResult(hit, face, support, false));
        client.player.swing(InteractionHand.MAIN_HAND);
        timer = VERIFY_TICKS;
        state = State.VERIFY;
    }

    private void verify(Minecraft client) {
        BlockState now = client.level.getBlockState(pos);
        if (!now.canBeReplaced()) {
            finish("SUCCESS", "placed " + idOf(now) + " at " + fmt(pos) + ".");
        } else {
            fail("FAILURE_NOT_PLACED", "the server did not accept the block at " + fmt(pos) + ".");
        }
    }

    private int findItem(Minecraft client) {
        var inv = client.player.getInventory();
        // hotbar first, so nothing is shuffled when it does not need to be
        for (int i = 0; i < 36; i++) {
            ItemStack s = inv.getItem(i);
            if (s.isEmpty() || !(s.getItem() instanceof BlockItem))
                continue;
            if (blockName == null || BuiltInRegistries.ITEM.getKey(s.getItem()).getPath().equals(blockName))
                return i;
        }
        return -1;
    }

    private boolean bodyInTheWay(Minecraft client) {
        return client.player.getBoundingBox().intersects(new AABB(pos));
    }

    private static String idOf(BlockState s) {
        return BuiltInRegistries.BLOCK.getKey(s.getBlock()).getPath();
    }

    private static String fmt(BlockPos p) {
        return "(" + p.getX() + ", " + p.getY() + ", " + p.getZ() + ")";
    }

    private void fail(String code, String why) {
        finish(code, why);
        LOGGER.info("place_block: " + why);
    }

    private void finish(String code, String why) {
        result = code;
        message = why;
        state = State.FINISHED;
    }

    @Override
    public void stop(Minecraft client) {
        state = State.FINISHED;
    }

    @Override
    public boolean isFinished() {
        return state == State.FINISHED;
    }

    @Override
    public String getResult() {
        return result;
    }

    @Override
    public JsonObject getFeedback() {
        JsonObject json = new JsonObject();
        json.addProperty("message", message);
        return json;
    }
}
```
Notes on the prototype: the verify step only checks "not replaceable any more" (a torch
becomes `wall_torch`, so exact-id checks need a block-family rule); `canBeReplaced()`
(no-arg) is the generic check — vanilla's context-aware variant would be more exact.
`isWithinBlockInteractionRange(support, 0.0)` is conservative (vanilla's server allows
+1.0).

### B.2 projectBEA (`main` @ `ef631d9`) — `src/core/skills/minecraft/client.py`
```diff
-PROTOCOL_VERSION = 1
+PROTOCOL_VERSION = 2
@@ def __init__
         self.actions: set = set()
+        self.protocol: int = 0
@@ def _handle
             observation = f"INTERRUPTED: {reason}"
             logger.warning(observation)
-            if not self._settle(observation, data.get("id")):
+            if self.protocol >= 2 and not data.get("id"):
+                self._events.put_nowait(observation)
+            elif not self._settle(observation, data.get("id")):
                 self._events.put_nowait(observation)
             return
 
         if status in _COMPLETION:
             result = data.get("result", "SUCCESS")
-            message = data.get("message", "")
-            observation = f"{result}" + (f": {message}" if message else "")
+            observation = f"{result}" + (f": {_message_of(data)}" if _message_of(data) else "")
+            if self.protocol >= 2 and not data.get("id"):
+                # the mod acted on its own (eating, self-defence): nobody asked for this
+                logger.debug(f"unsolicited completion: {observation}")
+                return
             self._settle(observation, data.get("id"))
@@ def _on_handshake
         protocol = data.get("protocol")
+        self.protocol = int(protocol or 0)
@@ end of file
+def _message_of(data: Dict[str, Any]) -> str:
+    """The mod nests its explanation under `details`; older packets put it on top."""
+    if data.get("message"):
+        return str(data["message"])
+    details = data.get("details")
+    if isinstance(details, dict):
+        return str(details.get("message") or details.get("error") or "")
+    return ""
```
(Prototype only: the production version also stops treating `chat`/`check_death_log` as
fire-and-forget, adds reflex events and per-action timeouts — Phase 1.)

---

## Appendix C — A real state packet rendered for the body (E-sight, original build)

Setup: oak tree at (7,-57,0), crafting table at (-3,-57,2), iron_ore at (12,-57,-3), a cow
at ~7 blocks, player at (0.5,-57,0.5) with a wooden pickaxe and 3 oak planks.
```
- health 17/20, food 5/20 at (0, -57, 0)
- holding: wooden_pickaxe; carrying: oak_planks×3, wooden_pickaxe×1
- can craft now: oak_pressure_plate, oak_button, stick, oak_slab
- nearby: crafting_table (-3, -57, 2) 3.6m
- standing on grass_block, air above your head
- surrounded by: dirt×162, grass_block×81, stone×81
- around you: Cow 7m
```
Missing: the tree, the ore, time of day; wrong: `oak_slab` (needs a 3-wide grid).
Raw packet: 3,349 chars; rendered: 336 chars.
