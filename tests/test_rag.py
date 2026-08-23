"""Long-term recall, with a deterministic embedder so similarity is predictable."""

import math
import time

import pytest

from src.core.memory.db import Database
from src.core.memory.rag import SOURCE_BEA, SOURCE_PERSON, Rag, cosine


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


def test_the_vector_path_and_the_python_path_return_the_same_thing(rag):
    """sqlite-vec is only a coarse pre-filter; the decision is the same cosine,
    so enabling it must not change results."""
    for text in ["marco adora minecraft", "luca parla di pizza", "musica di notte",
                 "il gatto dorme in casa"]:
        remember(rag, text)

    query = "minecraft e pizza"
    rag._vec_ready = False
    python_path = [r.text for r in rag.recall(query, scope="diary", scope_key="s1")]
    rag._vec_ready = bool(rag.db.vec_enabled)
    vec_path = [r.text for r in rag.recall(query, scope="diary", scope_key="s1")]
    assert python_path == vec_path


def test_similarity_is_reported_on_each_hit(rag):
    remember(rag, "marco adora minecraft")
    hit = rag.recall("minecraft", scope="diary", scope_key="s1")[0]
    assert 0.0 < hit.similarity <= 1.0
    assert not math.isnan(hit.similarity)
