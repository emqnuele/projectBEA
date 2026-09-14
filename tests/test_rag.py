"""Long-term recall, with a deterministic embedder so similarity is predictable."""

import math
import time

import pytest

from src.core.memory.db import Database
from src.core.memory.rag import SOURCE_BEA, SOURCE_PERSON, Rag, cosine
from src.core.perf import perf_enabled


class WordEmbedder:
    """Bag-of-words over a fixed vocabulary: deterministic, no model download.

    Two texts sharing words end up close; texts sharing nothing end up
    orthogonal. That is all the tests need, and it makes every assertion exact.
    """

    VOCAB = ["minecraft", "ferrari", "pizza", "casa", "notte", "musica", "gatto", "lavoro"]

    def __init__(self):
        self.calls = 0
        self.fail = False

    def embed(self, texts):
        self.calls += 1
        if self.fail:
            raise RuntimeError("embedder is down")
        out = []
        for text in texts:
            low = (text or "").lower()
            vec = [1.0 if word in low else 0.0 for word in self.VOCAB]
            if not any(vec):
                vec = [0.001] * len(self.VOCAB)
            out.append(vec)
        return out

    @property
    def dim(self):
        return len(self.VOCAB)


@pytest.fixture
def rag():
    db = Database(":memory:").init()
    yield Rag(db, WordEmbedder(), min_similarity=0.2)
    db.close()


def remember(rag, text, **kwargs):
    kwargs.setdefault("scope", "diary")
    kwargs.setdefault("scope_key", "s1")
    return rag.remember(text=text, **kwargs)


def index_active(rag):
    """The index answers only when it exists and the perf switch allows it."""
    return bool(rag.db.vec_enabled) and perf_enabled() and rag._vec_ready


# --- cosine -----------------------------------------------------------------


def test_identical_vectors_are_perfectly_similar():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_orthogonal_vectors_are_unrelated():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_a_zero_vector_is_similar_to_nothing():
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_magnitude_does_not_change_direction():
    assert cosine([1.0, 1.0], [5.0, 5.0]) == pytest.approx(1.0)


# --- writing ----------------------------------------------------------------


def test_a_memory_is_stored_with_its_vector(rag):
    assert remember(rag, "parliamo di minecraft") is not None
    assert rag.count() == 1


def test_a_fragment_is_not_worth_remembering(rag):
    assert remember(rag, "ok") is None
    assert rag.count() == 0


def test_the_same_memory_is_not_stored_twice(rag):
    remember(rag, "parliamo di minecraft")
    assert remember(rag, "parliamo di minecraft") is None
    assert rag.count() == 1


def test_the_same_text_in_another_scope_is_a_different_memory(rag):
    remember(rag, "parliamo di minecraft", scope_key="s1")
    remember(rag, "parliamo di minecraft", scope_key="s2")
    assert rag.count() == 2


def test_an_unknown_source_is_refused(rag):
    with pytest.raises(ValueError):
        remember(rag, "qualcosa di lungo", source="martian")


def test_a_broken_embedder_never_loses_the_memory(rag):
    """RAG must never break the main flow: keep the text, fill the vector later."""
    rag.embedder.fail = True
    assert remember(rag, "parliamo di minecraft") is not None
    assert rag.count() == 1


# --- recall -----------------------------------------------------------------


def test_recall_finds_the_related_memory(rag):
    remember(rag, "marco adora minecraft")
    remember(rag, "luca parla solo di pizza")
    found = rag.recall("minecraft", scope="diary", scope_key="s1")
    assert [r.text for r in found] == ["marco adora minecraft"]


def test_an_unrelated_query_finds_nothing(rag):
    remember(rag, "marco adora minecraft")
    assert rag.recall("gatto", scope="diary", scope_key="s1") == []


def test_an_empty_query_finds_nothing(rag):
    remember(rag, "marco adora minecraft")
    assert rag.recall("  ", scope="diary", scope_key="s1") == []


def test_recall_can_span_every_scope(rag):
    remember(rag, "marco adora minecraft", scope_key="s1")
    remember(rag, "anche luca gioca a minecraft", scope_key="s2")
    assert len(rag.recall("minecraft", scope="diary")) == 2


def test_a_broken_embedder_makes_recall_empty_not_fatal(rag):
    remember(rag, "marco adora minecraft")
    rag.embedder.fail = True
    assert rag.recall("minecraft", scope="diary", scope_key="s1") == []


def test_memories_without_a_vector_are_skipped_on_recall(rag):
    rag.embedder.fail = True
    remember(rag, "marco adora minecraft")
    rag.embedder.fail = False
    assert rag.recall("minecraft", scope="diary", scope_key="s1") == []


def test_a_recent_memory_outranks_an_equally_similar_old_one(rag):
    old = time.time() - 400 * 86400
    remember(rag, "vecchio ricordo su minecraft", created_at=old)
    remember(rag, "nuovo ricordo su minecraft")
    found = rag.recall("minecraft", scope="diary", scope_key="s1")
    assert found[0].text == "nuovo ricordo su minecraft"


def test_the_similarity_threshold_filters_noise(rag):
    rag.min_similarity = 0.99
    remember(rag, "marco adora minecraft e pizza")
    assert rag.recall("minecraft", scope="diary", scope_key="s1") == []


def test_a_recollection_renders_with_its_speaker(rag):
    remember(rag, "adoro minecraft", who="marco")
    assert rag.recall("minecraft", scope="diary", scope_key="s1")[0].render() == \
        "marco: adoro minecraft"


def test_a_recollection_without_a_speaker_renders_bare(rag):
    remember(rag, "si parlava di minecraft")
    assert rag.recall("minecraft", scope="diary", scope_key="s1")[0].render() == \
        "si parlava di minecraft"


# --- recall_split: facts vs her own inventions -------------------------------


def test_what_people_said_and_what_bea_said_come_back_separated(rag):
    """Bea invents on purpose. If her own lines re-entered the prompt as facts
    she would build on them as if they were true."""
    remember(rag, "marco ha una ferrari", who="marco", source=SOURCE_PERSON)
    remember(rag, "io ho tre ferrari", who="bea", source=SOURCE_BEA)

    facts, hers = rag.recall_split("ferrari", scope="diary", scope_key="s1")
    assert [r.text for r in facts] == ["marco ha una ferrari"]
    assert [r.text for r in hers] == ["io ho tre ferrari"]


def test_plain_recall_returns_only_the_facts(rag):
    remember(rag, "marco ha una ferrari", source=SOURCE_PERSON)
    remember(rag, "io ho tre ferrari", source=SOURCE_BEA)
    assert [r.text for r in rag.recall("ferrari", scope="diary", scope_key="s1")] == \
        ["marco ha una ferrari"]


def test_memories_default_to_being_someone_elses_words(rag):
    remember(rag, "qualcosa su minecraft")
    assert rag.recall("minecraft", scope="diary", scope_key="s1")[0].source == SOURCE_PERSON


# --- model changes -----------------------------------------------------------


def test_the_first_model_is_recorded_without_re_embedding(rag):
    remember(rag, "marco adora minecraft")
    assert rag.ensure_model("model-a") == 0


def test_the_same_model_is_a_no_op(rag):
    rag.ensure_model("model-a")
    remember(rag, "marco adora minecraft")
    assert rag.ensure_model("model-a") == 0


def test_changing_the_model_re_embeds_everything(rag):
    """Vectors from two models are not comparable: keeping the old ones would
    make every similarity a meaningless number."""
    rag.ensure_model("model-a")
    remember(rag, "marco adora minecraft")
    remember(rag, "luca parla di pizza")
    assert rag.ensure_model("model-b") == 2


def test_recall_still_works_after_a_model_change(rag):
    rag.ensure_model("model-a")
    remember(rag, "marco adora minecraft")
    rag.ensure_model("model-b")
    assert len(rag.recall("minecraft", scope="diary", scope_key="s1")) == 1


# --- writing is one transaction, and the text is what must survive ------------


def test_a_broken_index_never_loses_the_memory(rag):
    """The index is derived from the text. Losing the text to save it is backwards."""
    if not index_active(rag):
        pytest.skip("the vector index is not active here")
    rag.db.execute("DROP TABLE IF EXISTS vec_memories")
    assert remember(rag, "marco adora minecraft") is not None
    assert rag.count() == 1


def test_a_memory_and_its_vector_land_together(rag):
    if not index_active(rag):
        pytest.skip("the vector index is not active here")
    mem_id = remember(rag, "marco adora minecraft")
    indexed = rag.db.query("SELECT rowid FROM vec_memories WHERE rowid = ?", (mem_id,))
    assert len(indexed) == 1


def test_re_indexing_the_same_memory_replaces_it(rag):
    """`INSERT OR REPLACE` raises on a vec0 table, so this was write-once."""
    if not index_active(rag):
        pytest.skip("the vector index is not active here")
    mem_id = remember(rag, "marco adora minecraft")
    rag._index_vector(mem_id, "diary", "s1", rag.db.query_one(
        "SELECT embedding FROM memories WHERE id = ?", (mem_id,))["embedding"])
    assert len(rag.db.query("SELECT rowid FROM vec_memories WHERE rowid = ?", (mem_id,))) == 1


def test_forgetting_leaves_no_vectors_behind(rag):
    """Nothing points the index back at `memories`; an orphan would just sit there."""
    if not index_active(rag):
        pytest.skip("the vector index is not active here")
    remember(rag, "marco adora minecraft", scope_key="s1")
    remember(rag, "luca parla di pizza", scope_key="s2")
    rag.forget_scope("diary", "s1")
    assert len(rag.db.query("SELECT rowid FROM vec_memories")) == 1


# --- forgetting --------------------------------------------------------------


def test_a_whole_scope_can_be_forgotten(rag):
    remember(rag, "marco adora minecraft", scope_key="s1")
    remember(rag, "luca parla di pizza", scope_key="s2")
    assert rag.forget_scope("diary", "s1") == 1
    assert rag.count() == 1


def test_forgetting_an_empty_scope_removes_nothing(rag):
    assert rag.forget_scope("diary", "nothing") == 0


def test_one_person_can_ask_to_be_forgotten(rag):
    remember(rag, "marco adora minecraft", who_identity="discord:1")
    remember(rag, "luca parla di pizza", who_identity="discord:2")
    assert rag.forget_person("discord:1") == 1
    assert [r["text"] for r in rag.db.query("SELECT text FROM memories")] == \
        ["luca parla di pizza"]


def test_exists_reports_whether_a_scope_has_anything(rag):
    assert rag.exists("diary", "s1") is False
    remember(rag, "marco adora minecraft")
    assert rag.exists("diary", "s1") is True


# --- the two retrieval paths agree -------------------------------------------


def _both_paths(rag, query, **kw):
    """The same recall down each path. Returns (python, vec)."""
    was = rag._vec_ready
    rag._vec_ready = False
    python_path = [r.text for r in rag.recall(query, **kw)]
    rag._vec_ready = bool(rag.db.vec_enabled)
    vec_path = [r.text for r in rag.recall(query, **kw)]
    rag._vec_ready = was
    return python_path, vec_path


@pytest.mark.parametrize("scope_key", [None, "s1"])
def test_the_vector_path_and_the_python_path_return_the_same_thing(rag, scope_key):
    """The index answers with the same cosine, so turning it on changes nothing.

    Parametrised over `scope_key` because that is the whole story: every test
    here used to pass "s1", nothing in the engine passes anything, and the
    version of this file without the `None` case was green while production
    never once reached the index.
    """
    for text in ["marco adora minecraft", "luca parla di pizza", "musica di notte",
                 "il gatto dorme in casa"]:
        remember(rag, text)

    python_path, vec_path = _both_paths(rag, "minecraft e pizza",
                                        scope="diary", scope_key=scope_key)
    # distance and recency are identical for the top two, so the final order
    # depends on the raw sqlite select order, which varies across platforms.
    assert set(python_path) == set(vec_path)
    assert len(python_path) == len(vec_path)


@pytest.mark.parametrize("scope_key", [None, "s1"])
def test_the_paths_agree_on_a_store_big_enough_to_order(rag, scope_key):
    """Four memories can agree by luck. Two hundred have to agree on purpose."""
    words = WordEmbedder.VOCAB
    for i in range(200):
        remember(rag, f"ricordo {i} su {words[i % len(words)]} e {words[(i + 3) % len(words)]}",
                 scope_key="s1" if i % 2 else "s2",
                 source=SOURCE_BEA if i % 5 == 0 else SOURCE_PERSON,
                 created_at=time.time() - i * 86400)

    python_path, vec_path = _both_paths(rag, "minecraft e musica",
                                        scope="diary", scope_key=scope_key)
    assert python_path == vec_path
    assert python_path


def test_the_index_answers_a_recall_that_names_no_session(rag):
    """The regression, stated as a requirement.

    Nothing in the engine passes a scope_key when reading — `single_context`,
    the memory skill and the dashboard all pass a scope alone. If that query
    cannot be served from the index, the index is decoration. Breaking the scan
    is how this test can tell the difference: it only passes if the answer came
    from somewhere else.
    """
    if not index_active(rag):
        pytest.skip("the vector index is not active here")
    for text in ["marco adora minecraft", "luca parla di pizza"]:
        remember(rag, text)

    def unreachable(*a, **kw):
        raise AssertionError("recall fell back to the full scan")

    rag._recall_python = unreachable
    assert [r.text for r in rag.recall("minecraft", scope="diary")] == ["marco adora minecraft"]


def test_a_broken_index_still_answers_through_python(rag):
    """The fallback is the product, not a nicety."""
    for text in ["marco adora minecraft", "luca parla di pizza"]:
        remember(rag, text)
    rag.db.execute("DROP TABLE IF EXISTS vec_memories")
    assert [r.text for r in rag.recall("minecraft", scope="diary")] == ["marco adora minecraft"]


def test_scopes_do_not_leak_into_each_other(rag):
    """The reason the index is partitioned by scope and not by session."""
    remember(rag, "marco adora minecraft", scope="diary")
    remember(rag, "luca adora minecraft", scope="conversation")
    found = [r.text for r in rag.recall("minecraft", scope="diary")]
    assert found == ["marco adora minecraft"]


def test_more_candidates_than_one_round_trip(rag):
    """`_fetch` reads ids in chunks; the seam between them must change nothing."""
    from src.core.memory import rag as rag_module

    for i in range(40):
        remember(rag, f"ricordo numero {i} su minecraft")

    whole = [r.text for r in rag.recall("minecraft", scope="diary", k=30)]
    original = rag_module.FETCH_CHUNK
    rag_module.FETCH_CHUNK = 7
    try:
        split = [r.text for r in rag.recall("minecraft", scope="diary", k=30)]
    finally:
        rag_module.FETCH_CHUNK = original
    assert split == whole
    assert len(whole) == 30


# --- vectors that cannot be compared ------------------------------------------


def test_a_vector_without_direction_matches_nothing(rag):
    """A zero vector has no direction. It is unrelated, not undefined."""
    rag.db.execute(
        "INSERT INTO memories (scope, scope_key, who_name, text, source, embedding, "
        "tags, created_at) VALUES ('diary', 's1', '', 'un ricordo senza direzione', "
        "'person', ?, '', ?)",
        (b"\x00" * (4 * len(WordEmbedder.VOCAB)), time.time()))
    assert rag.recall("minecraft", scope="diary") == []


def test_memories_from_another_model_are_skipped_not_fatal(rag):
    """Mid re-embed a store holds both widths. The recall must still answer."""
    remember(rag, "marco adora minecraft")
    rag.db.execute(
        "INSERT INTO memories (scope, scope_key, who_name, text, source, embedding, "
        "tags, created_at) VALUES ('diary', 's1', '', 'un ricordo di un altro modello', "
        "'person', ?, '', ?)",
        (b"\x01" * 4 * 99, time.time()))
    assert [r.text for r in rag.recall("minecraft", scope="diary")] == ["marco adora minecraft"]


# --- the index is derived, and rebuilt when its shape changes -----------------


def test_an_old_index_is_rebuilt_from_the_vectors_already_stored(rag):
    """No re-embedding: every vector in the index is also in `memories`."""
    if not index_active(rag):
        pytest.skip("the vector index is not active here")
    for text in ["marco adora minecraft", "luca parla di pizza"]:
        remember(rag, text)

    # the shape this store used to have, and a store on disk still has
    rag.db.execute("DROP TABLE IF EXISTS vec_memories")
    with rag.db.cursor() as cur:
        cur.execute(f"CREATE VIRTUAL TABLE vec_memories USING vec0("
                    f"scope_key TEXT partition key, embedding float[{rag.embedder.dim}])")
    rag.db.execute("DELETE FROM memory_meta WHERE key = 'vec_schema'")

    rebuilt = Rag(rag.db, rag.embedder, min_similarity=0.2)
    assert rebuilt._vec_ready
    assert [r.text for r in rebuilt.recall("minecraft", scope="diary")] == \
        ["marco adora minecraft"]


def test_the_index_is_not_rebuilt_on_every_start(rag):
    """Rebuilding is cheap, not free; doing it each time is a startup cost."""
    if not index_active(rag):
        pytest.skip("the vector index is not active here")
    remember(rag, "marco adora minecraft")
    before = rag.db.query_one("SELECT value FROM memory_meta WHERE key = 'vec_schema'")
    again = Rag(rag.db, rag.embedder, min_similarity=0.2)
    after = rag.db.query_one("SELECT value FROM memory_meta WHERE key = 'vec_schema'")
    assert again._vec_ready
    assert before["value"] == after["value"]
    assert rag.db.query("SELECT rowid FROM vec_memories")


def test_wiring_recall_never_loads_the_embedding_model(rag):
    """Startup asks the embedder how wide it is, and nothing more.

    Measuring that width by embedding a throwaway string loaded the model — a
    220MB download, during startup, from a class whose whole point is being
    lazy about exactly that.
    """
    class WidthOnly:
        dim = 8

        def embed(self, texts):
            raise AssertionError("the model was loaded to wire up recall")

    db = Database(":memory:").init()
    try:
        Rag(db, WidthOnly())
    finally:
        db.close()


def test_similarity_is_reported_on_each_hit(rag):
    remember(rag, "marco adora minecraft")
    hit = rag.recall("minecraft", scope="diary", scope_key="s1")[0]
    assert 0.0 < hit.similarity <= 1.0
    assert not math.isnan(hit.similarity)
