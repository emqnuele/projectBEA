"""The unified store: one transactional file instead of five drifting ones."""

import time

import pytest

from src.core.memory.store import MAX_FACTS_STORED, MemoryStore


@pytest.fixture
def store():
    s = MemoryStore(":memory:")
    yield s
    s.close()


def see(store, identity="discord:1", name="marco", platform="discord", **kwargs):
    return store.roster.record(identity=identity, display_name=name, platform=platform, **kwargs)


# --- roster -----------------------------------------------------------------


def test_an_unknown_identity_is_none(store):
    assert store.roster.get("discord:nobody") is None


def test_a_first_sighting_creates_the_tally(store):
    entry = see(store)
    assert entry.identity == "discord:1"
    assert entry.display_name == "marco"
    assert entry.message_count == 1
    assert entry.promoted is False


def test_sightings_accumulate_instead_of_rewriting(store):
    for _ in range(5):
        see(store)
    assert store.roster.get("discord:1").message_count == 5


def test_distinct_sessions_are_what_count(store):
    see(store, session_id="s1")
    see(store, session_id="s1")
    see(store, session_id="s2")
    entry = store.roster.get("discord:1")
    assert entry.message_count == 3
    assert entry.session_count == 2


def test_a_display_name_change_is_kept(store):
    see(store, name="marco")
    see(store, name="marco_new")
    assert store.roster.get("discord:1").display_name == "marco_new"


def test_a_blank_name_does_not_wipe_the_one_we_have(store):
    see(store, name="marco")
    see(store, name="")
    assert store.roster.get("discord:1").display_name == "marco"


def test_donations_add_up(store):
    see(store, donation=5.0)
    see(store, donation=2.5)
    assert store.roster.get("discord:1").donation_total == 7.5


def test_a_one_on_one_sticks_once_true(store):
    see(store, is_1on1=True)
    see(store, is_1on1=False)
    assert store.roster.get("discord:1").had_1on1 is True


def test_bea_can_mark_someone(store):
    see(store)
    assert store.roster.mark("discord:1").marked_by_bea is True


def test_find_by_name_matches_exactly_first(store):
    see(store, identity="discord:1", name="marco")
    see(store, identity="discord:2", name="marcolino")
    assert store.roster.find_by_name("marco").identity == "discord:1"


def test_find_by_name_falls_back_to_a_partial_match(store):
    see(store, identity="discord:2", name="marcolino")
    assert store.roster.find_by_name("marcol").identity == "discord:2"


def test_find_by_name_of_a_stranger_is_none(store):
    assert store.roster.find_by_name("nessuno") is None


def test_the_roster_lists_everyone(store):
    see(store, identity="discord:1", name="marco")
    see(store, identity="twitch:9", name="luca", platform="twitch")
    assert {e.identity for e in store.roster.all()} == {"discord:1", "twitch:9"}


def test_regulars_are_ordered_by_how_much_they_talk(store):
    for _ in range(3):
        see(store, identity="discord:1", name="marco")
    see(store, identity="discord:2", name="luca")
    assert [e.identity for e in store.roster.regulars()] == ["discord:1", "discord:2"]


# --- people -----------------------------------------------------------------


def promote(store, identity="discord:1", **kwargs):
    entry = store.roster.get(identity)
    card = store.people.create_from_entry(entry, **kwargs)
    store.roster.set_promoted(identity, card.person_id)
    return card


def test_promotion_links_the_identity_to_the_card(store):
    see(store)
    card = promote(store, reason="a regular")
    assert store.people.get_by_identity("discord:1").person_id == card.person_id
    assert store.roster.get("discord:1").promoted is True
    assert store.roster.get("discord:1").person_id == card.person_id


def test_a_card_carries_its_promotion_reason(store):
    see(store)
    assert promote(store, reason="donated").promoted_reason == "donated"


def test_seed_facts_land_on_the_card(store):
    see(store)
    card = promote(store, seed_facts=["first noticed today"])
    assert store.people.get(card.person_id).facts == ["first noticed today"]


def test_facts_accumulate_in_order(store):
    see(store)
    card = promote(store)
    store.people.add_fact(card.person_id, "loves minecraft")
    store.people.add_fact(card.person_id, "hates mornings")
    assert store.people.get(card.person_id).facts == ["loves minecraft", "hates mornings"]


def test_the_same_fact_is_never_stored_twice(store):
    see(store)
    card = promote(store)
    store.people.add_fact(card.person_id, "loves minecraft")
    store.people.add_fact(card.person_id, "loves minecraft")
    assert store.people.get(card.person_id).facts == ["loves minecraft"]


def test_a_card_never_grows_without_bound(store):
    """An unbounded card would eventually eat the prompt."""
    see(store)
    card = promote(store)
    for i in range(MAX_FACTS_STORED + 10):
        store.people.add_fact(card.person_id, f"fact {i}")
    facts = store.people.get(card.person_id).facts
    assert len(facts) == MAX_FACTS_STORED
    assert facts[-1] == f"fact {MAX_FACTS_STORED + 9}"


def test_facts_for_an_unknown_person_are_ignored(store):
    store.people.add_fact("no-such-person", "something")
    assert store.people.all() == []


def test_an_attitude_can_be_set(store):
    see(store)
    card = promote(store)
    store.people.set_attitude(card.person_id, "tollerabile")
    assert store.people.get(card.person_id).bea_attitude == "tollerabile"


def test_a_card_renders_for_the_prompt(store):
    see(store)
    card = promote(store)
    store.people.set_attitude(card.person_id, "tollerabile")
    store.people.add_fact(card.person_id, "loves minecraft")
    assert store.people.get(card.person_id).render() == \
        "- **marco** (you: tollerabile): loves minecraft"


def test_a_card_can_be_found_by_name(store):
    see(store)
    promote(store)
    assert store.people.find_by_name("marco") is not None
    assert store.people.find_by_name("nessuno") is None


def test_two_identities_can_be_the_same_person(store):
    """Cross-platform merge: one person, two accounts. Never automatic."""
    see(store, identity="discord:1", name="marco")
    see(store, identity="minecraft:uuid-1", name="Marco", platform="minecraft")
    card = promote(store, "discord:1")
    store.people.link_identity(card.person_id, "minecraft:uuid-1")

    from_game = store.people.get_by_identity("minecraft:uuid-1")
    assert from_game.person_id == card.person_id
    assert set(from_game.identities) == {"discord:1", "minecraft:uuid-1"}


# --- hot facts --------------------------------------------------------------


def test_a_fresh_hot_fact_is_active(store):
    store.hot.add("marco just donated", 3600)
    assert [f.text for f in store.hot.active()] == ["marco just donated"]


def test_an_expired_hot_fact_is_gone(store):
    store.hot.add("stale", -1)
    assert store.hot.active() == []


def test_a_blank_hot_fact_is_ignored(store):
    store.hot.add("   ", 3600)
    assert store.hot.active() == []


def test_the_same_hot_fact_refreshes_instead_of_duplicating(store):
    store.hot.add("your birthday is in 3 days", 10, source="morning_pass")
    store.hot.add("your birthday is in 3 days", 3600, source="morning_pass")
    facts = store.hot.active()
    assert len(facts) == 1 and facts[0].expires_at > time.time() + 100


def test_the_same_text_from_another_source_is_kept(store):
    store.hot.add("same", 3600, source="morning_pass")
    store.hot.add("same", 3600, source="dreamer")
    assert len(store.hot.active()) == 2


def test_clearing_a_source_leaves_the_others(store):
    store.hot.add("derived", 3600, source="morning_pass")
    store.hot.add("dreamt", 3600, source="dreamer")
    store.hot.clear_source("morning_pass")
    assert [f.text for f in store.hot.active()] == ["dreamt"]


def test_hot_facts_render_capped(store):
    for i in range(10):
        store.hot.add(f"fact {i}", 3600)
    assert store.hot.render(max_items=3).count("\n- ") == 3


def test_rendering_nothing_is_empty(store):
    assert store.hot.render() == ""


# --- self -------------------------------------------------------------------


def test_self_facts_accumulate(store):
    assert store.selflore.append_fact("you hate mondays") is True
    assert store.selflore.facts() == ["you hate mondays"]


def test_the_same_self_fact_is_not_added_twice(store):
    store.selflore.append_fact("you hate mondays")
    assert store.selflore.append_fact("you hate mondays") is False
    assert len(store.selflore.facts()) == 1


def test_a_blank_self_fact_is_refused(store):
    assert store.selflore.append_fact("   ") is False


def test_a_leading_bullet_is_stripped(store):
    store.selflore.append_fact("- you hate mondays")
    assert store.selflore.facts() == ["you hate mondays"]


def test_the_self_prompt_view_is_capped(store):
    for i in range(30):
        store.selflore.append_fact(f"fact {i}")
    rendered = store.selflore.render_for_prompt(max_facts=5)
    assert rendered.count("\n") == 4
    assert "fact 29" in rendered and "fact 0" not in rendered


def test_the_profile_holds_structured_bits(store):
    store.selflore.update_profile({"birthday": "03-14"})
    assert store.selflore.profile()["birthday"] == "03-14"


def test_updating_the_profile_ignores_blanks(store):
    store.selflore.update_profile({"birthday": "03-14"})
    store.selflore.update_profile({"birthday": "", "other": None})
    assert store.selflore.profile() == {"birthday": "03-14"}


# --- conversations ----------------------------------------------------------


def test_conversation_history_reads_oldest_first(store):
    for i in range(3):
        store.conversations.add(conversation_key="discord:1", role="user", content=f"m{i}")
    assert [m["content"] for m in store.conversations.history("discord:1")] == ["m0", "m1", "m2"]


def test_history_is_limited_to_the_most_recent(store):
    for i in range(10):
        store.conversations.add(conversation_key="discord:1", role="user", content=f"m{i}")
    assert [m["content"] for m in store.conversations.history("discord:1", limit=3)] == \
        ["m7", "m8", "m9"]


def test_conversations_are_kept_apart(store):
    store.conversations.add(conversation_key="discord:1", role="user", content="qua")
    store.conversations.add(conversation_key="discord:2", role="user", content="la")
    assert [m["content"] for m in store.conversations.history("discord:1")] == ["qua"]


def test_seconds_since_bea_spoke_is_none_before_she_does(store):
    store.conversations.add(conversation_key="discord:1", role="user", content="ciao")
    assert store.conversations.seconds_since_bea_spoke("discord:1") is None


def test_seconds_since_bea_spoke_tracks_her_last_line(store):
    store.conversations.add(conversation_key="discord:1", role="bea", content="eccomi")
    assert store.conversations.seconds_since_bea_spoke("discord:1") < 5


def test_recent_activity_counts_only_people(store):
    store.conversations.add(conversation_key="discord:1", role="user", content="a")
    store.conversations.add(conversation_key="discord:1", role="bea", content="b")
    assert store.conversations.recent_activity("discord:1") == 1


def test_old_messages_fall_out_of_the_activity_window(store):
    store.conversations.add(conversation_key="discord:1", role="user", content="vecchio",
                            ts=time.time() - 500)
    assert store.conversations.recent_activity("discord:1", window_seconds=120) == 0


def test_a_summary_round_trips(store):
    store.conversations.save_summary("discord:1", "parlano di minecraft")
    assert store.conversations.summary("discord:1") == "parlano di minecraft"


def test_no_summary_yet_is_empty(store):
    assert store.conversations.summary("discord:1") == ""


def test_a_summary_is_due_after_enough_new_messages(store):
    for _ in range(5):
        store.conversations.add(conversation_key="discord:1", role="user", content="x")
    assert store.conversations.summary_due("discord:1", every=5) is True
    store.conversations.mark_summarized("discord:1")
    assert store.conversations.summary_due("discord:1", every=5) is False


def test_the_trigger_is_a_delta_not_a_modulo(store):
    """The check only runs when Bea answers, so the counter jumps: an exact
    multiple would be stepped over and the summary would never refresh."""
    for _ in range(4):
        store.conversations.add(conversation_key="discord:1", role="user", content="x")
    store.conversations.mark_summarized("discord:1")
    for _ in range(7):  # jumps straight past 5 and 10
        store.conversations.add(conversation_key="discord:1", role="user", content="x")
    assert store.conversations.summary_due("discord:1", every=5) is True


def test_pruning_caps_history_per_conversation(store):
    for i in range(20):
        store.conversations.add(conversation_key="discord:1", role="user", content=f"m{i}")
    removed = store.conversations.prune(keep_per_conversation=5)
    assert removed == 15
    assert store.conversations.count("discord:1") == 5
    assert [m["content"] for m in store.conversations.history("discord:1")][0] == "m15"


# --- sessions ---------------------------------------------------------------


def test_a_session_can_be_titled(store):
    store.sessions.set_title("session_1", "la sera in cui marco e' sparito")
    row = store.db.query_one("SELECT title FROM sessions WHERE session_id = 'session_1'")
    assert row["title"] == "la sera in cui marco e' sparito"


def test_dreamed_sessions_are_tracked(store):
    store.sessions.record("session_1")
    store.sessions.record("session_2")
    store.sessions.mark_dreamed("session_1")
    assert store.sessions.dreamed() == {"session_1"}


def test_marking_dreamed_twice_is_harmless(store):
    store.sessions.mark_dreamed("session_1")
    store.sessions.mark_dreamed("session_1")
    assert store.sessions.dreamed() == {"session_1"}


# --- durability -------------------------------------------------------------


def test_everything_survives_a_reopen(tmp_path):
    path = str(tmp_path / "bea.db")
    first = MemoryStore(path)
    see(first, session_id="s1")
    first.hot.add("qualcosa", 3600)
    first.selflore.append_fact("you exist")
    first.close()

    second = MemoryStore(path)
    assert second.roster.get("discord:1").message_count == 1
    assert len(second.hot.active()) == 1
    assert second.selflore.facts() == ["you exist"]
    second.close()


# --- migrating an existing config --------------------------------------------


def test_the_old_chroma_sentinel_is_migrated():
    """An existing config.json still says `embedding_model: "local"`, which
    fastembed rejects outright."""
    from src.core.memory.embedder import DEFAULT_MODEL, resolve_model

    assert resolve_model("local") == DEFAULT_MODEL
    assert resolve_model("default") == DEFAULT_MODEL
    assert resolve_model("") == DEFAULT_MODEL
    assert resolve_model(None) == DEFAULT_MODEL


def test_a_real_model_name_is_left_alone():
    from src.core.memory.embedder import resolve_model

    assert resolve_model("BAAI/bge-small-en-v1.5") == "BAAI/bge-small-en-v1.5"
