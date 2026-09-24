"""The dream writes what it learned on the card the live prompt reads.

The pass names people, and a name used to be resolved on its own: the first
card answering to it got the facts, while the prompt in a call read the
card of the account actually speaking. One human became two half-cards. The
sitting knows which account spoke under which name, so the dream asks it.
"""

import pytest

from src.core.memory.store import MemoryStore
from src.core.skills.dream.dreamer import MAX_DREAM_ATTEMPTS, Dreamer
from src.core.skills.social.people import promote_entry, resolve_or_create_card

SESSION = "session_tonight"


class ScriptedLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    async def complete_json(self, user_input, system_prompt=None, history=None):
        self.calls += 1
        reply = self.replies[min(self.calls, len(self.replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply


class History:
    def set_session_title(self, session_id, title):
        return True


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    yield store
    store.close()


def said(memory, identity="discord:7", name="marco", session=SESSION):
    for role, text in (("user", f"[{name}] ciao bea"), ("bea", "ciao!")):
        memory.conversations.add(
            conversation_key="discord:1", role=role, content=text,
            author_identity=identity if role == "user" else None,
            display_name=name if role == "user" else "bea", session_id=session)


def dreamer(memory, llm) -> Dreamer:
    return Dreamer(llm=llm, history_manager=History(), roster=memory.roster,
                   people=memory.people, selflore=memory.selflore, recent=memory.hot,
                   sessions=memory.sessions, conversations=memory.conversations)


def about(name, fact):
    return {"title": "una sera", "people": [{"name": name, "facts": [fact],
                                             "attitude": "simpatico"}]}


def account_card(memory, identity="discord:7", name="marco", session="s0"):
    entry = memory.roster.record(identity=identity, display_name=name,
                                 platform=identity.split(":")[0], session_id=session,
                                 is_1on1=True)
    return promote_entry(memory.roster, memory.people, entry)


async def test_the_dream_writes_on_the_card_of_the_account_that_spoke(memory):
    named = resolve_or_create_card(memory.roster, memory.people, "marco")
    # a card minted by identity before the name was checked
    entry = memory.roster.record(identity="discord:7", display_name="marco",
                                 platform="discord", session_id="s0", is_1on1=True)
    mine = memory.people.create_from_entry(entry)
    memory.roster.set_promoted(entry.identity, mine.person_id)
    said(memory)

    await dreamer(memory, ScriptedLLM(about("marco", "plays redstone"))).run()

    assert "plays redstone" in memory.people.get(mine.person_id).facts
    assert "plays redstone" not in memory.people.get(named.person_id).facts
    assert memory.people.get(mine.person_id).bea_attitude == "simpatico"


async def test_the_dream_counts_no_second_sighting_of_a_speaker(memory):
    account_card(memory)
    said(memory)
    before = memory.roster.get("discord:7")

    await dreamer(memory, ScriptedLLM(about("marco", "plays redstone"))).run()

    after = memory.roster.get("discord:7")
    assert (after.message_count, after.session_count) == (before.message_count,
                                                          before.session_count)


async def test_a_speaker_below_the_thresholds_joins_the_name_only_card(memory):
    named = resolve_or_create_card(memory.roster, memory.people, "marco")
    memory.roster.record(identity="discord:7", display_name="marco", platform="discord",
                         session_id=SESSION)
    said(memory)

    await dreamer(memory, ScriptedLLM(about("marco", "plays redstone"))).run()

    card = memory.people.get(named.person_id)
    assert "discord:7" in card.identities
    assert "plays redstone" in card.facts
    assert memory.people.count() == 1


async def test_a_speaker_below_the_thresholds_earns_no_card(memory):
    memory.roster.record(identity="discord:7", display_name="marco", platform="discord",
                         session_id=SESSION)
    said(memory)

    await dreamer(memory, ScriptedLLM(about("marco", "plays redstone"))).run()

    assert memory.people.count() == 0


async def test_someone_only_talked_about_keeps_the_name_path(memory):
    named = resolve_or_create_card(memory.roster, memory.people, "luca")
    said(memory)

    await dreamer(memory, ScriptedLLM(about("luca", "is marco's brother"))).run()

    assert "is marco's brother" in memory.people.get(named.person_id).facts


async def test_a_name_two_accounts_spoke_under_is_not_guessed(memory):
    first = account_card(memory, "discord:7", session="s0")
    second = account_card(memory, "twitch:9", session="s1")
    assert first.person_id != second.person_id
    said(memory, "discord:7")
    said(memory, "twitch:9")

    await dreamer(memory, ScriptedLLM(about("marco", "plays redstone"))).run()

    # no account wins on its own: the name path writes to the oldest card, as before
    assert "plays redstone" in memory.people.get(first.person_id).facts
    assert "plays redstone" not in memory.people.get(second.person_id).facts


# --- a reply that is not a consolidation ----------------------------------------

@pytest.mark.parametrize("reply", [RuntimeError("provider 502"), {}, {".github": 1}])
async def test_an_unusable_reply_leaves_the_sitting_for_the_next_dream(memory, reply):
    said(memory)

    summary = await dreamer(memory, ScriptedLLM(reply)).run()

    assert SESSION not in memory.sessions.dreamed()
    assert summary["failed"] == 1 and summary["sessions"] == 0


async def test_the_next_dream_consolidates_what_failed(memory):
    account_card(memory)
    said(memory)
    llm = ScriptedLLM({}, about("marco", "plays redstone"))

    await dreamer(memory, llm).run()
    summary = await dreamer(memory, llm).run()

    assert summary["sessions"] == 1
    assert SESSION in memory.sessions.dreamed()
    assert "plays redstone" in memory.people.get_by_identity("discord:7").facts


async def test_a_sitting_that_always_fails_is_given_up_on(memory):
    said(memory)
    llm = ScriptedLLM({})

    for _ in range(MAX_DREAM_ATTEMPTS):
        await dreamer(memory, llm).run()
    await dreamer(memory, llm).run()

    assert SESSION in memory.sessions.dreamed()
    assert llm.calls == MAX_DREAM_ATTEMPTS


async def test_every_sitting_read_is_listed_for_the_diary(memory):
    said(memory, session="s_a")
    said(memory, session="s_b")
    memory.conversations.add(conversation_key="stage", role="world", kind="system",
                             content="started", session_id="s_quiet")

    summary = await dreamer(memory, ScriptedLLM({}, {"title": "ok"})).run()

    assert summary["sittings"] == ["s_a", "s_b"]


# --- what the pass hands back, as it hands it back ------------------------------

async def test_a_fact_wrapped_in_an_object_is_kept_as_its_text(memory):
    account_card(memory)
    said(memory)
    reply = {"title": "una sera",
             "self_facts": [{"fact": "she has a website"}, None, 3],
             "people": [{"name": "marco", "facts": [{"text": "plays redstone"}, ""]}]}

    await dreamer(memory, ScriptedLLM(reply)).run()

    assert memory.selflore.facts() == ["she has a website"]
    assert memory.people.get_by_identity("discord:7").facts[-1] == "plays redstone"


async def test_the_pass_is_told_what_she_already_knows_about_herself(memory):
    memory.selflore.append_fact("she has a website")
    said(memory)
    seen = []

    class Recording(ScriptedLLM):
        async def complete_json(self, user_input, system_prompt=None, history=None):
            seen.append(user_input)
            return {"title": "ok"}

    await dreamer(memory, Recording()).run()

    assert seen[0].startswith("ALREADY KNOWN ABOUT YOU:\n- she has a website\n")
    assert "CONVERSATION:" in seen[0]
