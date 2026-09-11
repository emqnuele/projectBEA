"""What the updater must never do to somebody's install.

Every test here runs against real git repositories built in a temp directory —
a bare "origin" and a clone of it — because the whole feature is an argument
about what git does when two people change the same file, and a mocked git
would only ever confirm what we already believe.

The shape of the suite follows the shape of the problem. A file being updated
is in one of four states, and three of them are trivial:

    |                  | upstream unchanged | upstream changed |
    | user untouched   | nothing to do      | git updates it   |
    | user edited      | keep theirs        | ← the real work  |

The last cell is where a naive updater silently destroys either the character
someone wrote or the engine improvements they were owed, so most of what
follows is about that one cell, and about what happens when the user ignores
the result and updates again.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from src.core.update import backup, lock, runner, state
from src.core.update.gitrepo import Repo
from src.core.update.reconcile import CONFLICT, KEPT, MERGED, REMOVED, UNTOUCHED, new_file_for
from src.core.update.runner import BLOCKED, CURRENT, UPDATED

# these build real repositories to test against, so they are the one part of
# the suite that cannot run without git. The engine can: nothing outside
# `src/core/update` ever shells out to it, which is why the updater degrades
# into a message instead of a failure.
pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git is not installed; the updater is unavailable, the engine is not",
)

SOUL = "data/prompts/soul.md"
OPERATING = "data/prompts/operating.md"

# three paragraphs far enough apart that a change to one never lands in the
# same merge hunk as a change to another — that is what makes the "both sides
# edited, cleanly" case deterministic rather than a coin toss on diff context
ORIGINAL = "\n".join([
    "# Operating manual",
    "",
    "## Identity",
    "She is curious.",
    "",
    "filler a",
    "filler b",
    "filler c",
    "filler d",
    "filler e",
    "filler f",
    "filler g",
    "filler h",
    "",
    "## Speaking",
    "Use the speak tool.",
    "",
])


def git(cwd: Path, *args: str) -> str:
    # the developer's own git config is kept out of these fixtures, but the
    # PATH is inherited: git lives somewhere else entirely on windows, and a
    # hardcoded posix one made the suite unrunnable there
    env = {**os.environ,
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "HOME": str(cwd), "USERPROFILE": str(cwd)}
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


def commit(cwd: Path, message: str) -> str:
    git(cwd, "add", "-A")
    git(cwd, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", message)
    return git(cwd, "rev-parse", "HEAD")


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def replace(root: Path, relative: str, old: str, new: str) -> None:
    text = read(root, relative)
    assert old in text, f"{old!r} is not in {relative}; the fixture drifted"
    write(root, relative, text.replace(old, new))


@pytest.fixture
def world(tmp_path, monkeypatch):
    """An upstream repository and somebody's clone of it."""
    monkeypatch.setattr(runner, "_cached", None)

    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-q")
    # git's default branch name has changed over the years; pin it either way
    git(upstream, "symbolic-ref", "HEAD", "refs/heads/main")
    write(upstream, SOUL, "# Soul\n\nShe is the one we ship.\n")
    write(upstream, OPERATING, ORIGINAL)
    write(upstream, "src/core/brain.py", "print('engine')\n")
    write(upstream, "uv.lock", "lock = 1\n")
    commit(upstream, "initial")

    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(upstream), str(clone))
    return upstream, clone


def update(clone: Path, **kwargs) -> runner.Report:
    runner.invalidate()
    return runner.apply(root=clone, source="test", **kwargs)


def bases(clone: Path) -> dict:
    return state.load(clone).bases


# --- the three easy quadrants -------------------------------------------------


def test_a_file_nobody_edited_just_becomes_the_new_one(world):
    upstream, clone = world
    replace(upstream, OPERATING, "Use the speak tool.", "Use the speak tool, always.")
    head = commit(upstream, "clarify speaking")

    report = update(clone)

    assert report.status == UPDATED
    assert "Use the speak tool, always." in read(clone, OPERATING)
    assert report.prompts == [], "a file the user never touched is not worth reporting"
    assert bases(clone)[OPERATING] == head


def test_an_edited_file_untouched_upstream_is_kept(world):
    upstream, clone = world
    write(clone, SOUL, "# Soul\n\nShe is mine.\n")
    replace(upstream, OPERATING, "She is curious.", "She is curious and blunt.")
    head = commit(upstream, "tune identity")

    report = update(clone)

    assert report.status == UPDATED
    assert read(clone, SOUL) == "# Soul\n\nShe is mine.\n"
    assert [o.state for o in report.prompts] == [KEPT]
    assert bases(clone)[SOUL] == head


def test_an_edit_identical_to_the_new_version_is_a_no_op(world):
    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is curious and blunt.")
    replace(upstream, OPERATING, "She is curious.", "She is curious and blunt.")
    head = commit(upstream, "same change")

    report = update(clone)

    assert [o.state for o in report.prompts] == [UNTOUCHED]
    assert bases(clone)[OPERATING] == head


# --- the quadrant the whole thing exists for ----------------------------------


def test_edits_on_both_sides_are_combined(world):
    """The case that rules out both naive answers.

    The user rewrote the identity paragraph; upstream improved the speaking
    instructions. Taking theirs loses her character, keeping ours freezes the
    engine's own manual. Both have to survive.
    """
    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic and tired.")
    replace(upstream, OPERATING, "Use the speak tool.", "Use the speak tool, never narrate.")
    head = commit(upstream, "improve the manual")

    report = update(clone)

    merged = read(clone, OPERATING)
    assert "She is sarcastic and tired." in merged, "the user's character was dropped"
    assert "Use the speak tool, never narrate." in merged, "the engine improvement was dropped"
    assert [o.state for o in report.prompts] == [MERGED]
    assert bases(clone)[OPERATING] == head
    assert not new_file_for(clone, OPERATING).exists()


def test_a_collision_leaves_the_users_file_exactly_as_it_was(world):
    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")
    replace(upstream, OPERATING, "She is curious.", "She is warm.")
    commit(upstream, "different identity")
    mine = read(clone, OPERATING)

    report = update(clone)

    assert [o.state for o in report.prompts] == [CONFLICT]
    assert read(clone, OPERATING) == mine
    assert "She is warm." in new_file_for(clone, OPERATING).read_text(encoding="utf-8")


def test_a_collision_never_writes_conflict_markers(world):
    """The one rule. `<<<<<<<` in a prompt is a system prompt that has gone mad."""
    upstream, clone = world
    replace(clone, SOUL, "She is the one we ship.", "She is mine.")
    replace(upstream, SOUL, "She is the one we ship.", "She is ours.")
    commit(upstream, "reword the shipped soul")

    update(clone)

    for marker in ("<<<<<<<", "=======", ">>>>>>>"):
        assert marker not in read(clone, SOUL)


def test_a_collision_does_not_move_the_base(world):
    """Nothing was reconciled, so the file is still built on the old revision."""
    upstream, clone = world
    start = Repo(clone).head()
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")
    replace(upstream, OPERATING, "She is curious.", "She is warm.")
    commit(upstream, "different identity")

    update(clone)

    assert bases(clone).get(OPERATING) in (None, start)


# --- updating again on top of a conflict nobody resolved ----------------------


def test_a_second_update_still_offers_the_changes_the_first_one_could_not_apply(world):
    """The reason the base is tracked per file instead of being taken as HEAD.

    The user ignored the first conflict. If the second update merged from the
    new HEAD instead of from where their file actually branched, the changes
    they never took would read as deletions they made — and would be dropped
    for good, silently.
    """
    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")

    replace(upstream, OPERATING, "She is curious.", "She is warm.")
    commit(upstream, "identity, colliding")
    update(clone)
    assert new_file_for(clone, OPERATING).exists()

    replace(upstream, OPERATING, "Use the speak tool.", "Use the speak tool, never narrate.")
    commit(upstream, "speaking, not colliding")
    report = update(clone)

    offered = new_file_for(clone, OPERATING).read_text(encoding="utf-8")
    assert "Use the speak tool, never narrate." in offered, "the newest change was not carried into .new"
    assert "She is warm." in offered, "the change from the first update was lost"
    assert [o.state for o in report.prompts] == [CONFLICT]
    assert read(clone, OPERATING).count("She is sarcastic.") == 1


def test_the_stale_new_file_is_replaced_not_accumulated(world):
    upstream, clone = world
    replace(clone, SOUL, "She is the one we ship.", "She is mine.")

    replace(upstream, SOUL, "She is the one we ship.", "Draft one.")
    commit(upstream, "first")
    update(clone)

    replace(upstream, SOUL, "Draft one.", "Draft two.")
    commit(upstream, "second")
    update(clone)

    offered = new_file_for(clone, SOUL).read_text(encoding="utf-8")
    assert "Draft two." in offered
    assert "Draft one." not in offered
    assert not (clone / (SOUL + ".new.new")).exists()


def test_a_conflict_that_stops_colliding_clears_itself(world):
    """Upstream moved its change elsewhere, so the merge now lands. No leftovers."""
    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")

    replace(upstream, OPERATING, "She is curious.", "She is warm.")
    commit(upstream, "colliding")
    update(clone)
    assert new_file_for(clone, OPERATING).exists()

    replace(upstream, OPERATING, "She is warm.", "She is curious.")
    replace(upstream, OPERATING, "Use the speak tool.", "Use the speak tool, briefly.")
    head = commit(upstream, "reverted, and something else")
    report = update(clone)

    assert [o.state for o in report.prompts] == [MERGED]
    assert not new_file_for(clone, OPERATING).exists(), "a resolved conflict left its .new behind"
    assert "She is sarcastic." in read(clone, OPERATING)
    assert "Use the speak tool, briefly." in read(clone, OPERATING)
    assert bases(clone)[OPERATING] == head


# --- the human ending to a conflict -------------------------------------------


def test_keeping_mine_clears_the_review_and_advances_the_base(world):
    from src.core.update.reconcile import resolve

    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")
    replace(upstream, OPERATING, "She is curious.", "She is warm.")
    commit(upstream, "colliding")
    update(clone)

    repo = Repo(clone)
    outcome = resolve(clone, repo, OPERATING, "mine", repo.head())

    assert outcome.base == repo.head()
    assert not new_file_for(clone, OPERATING).exists()
    assert "She is sarcastic." in read(clone, OPERATING)


def test_taking_theirs_replaces_the_file(world):
    from src.core.update.reconcile import resolve

    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")
    replace(upstream, OPERATING, "She is curious.", "She is warm.")
    commit(upstream, "colliding")
    update(clone)

    repo = Repo(clone)
    resolve(clone, repo, OPERATING, "theirs", repo.head())

    assert "She is warm." in read(clone, OPERATING)
    assert "She is sarcastic." not in read(clone, OPERATING)
    assert not new_file_for(clone, OPERATING).exists()


def test_after_resolving_the_next_update_does_not_replay_the_same_change(world):
    """What the explicit resolution buys: the base moved, so the delta is not re-applied."""
    from src.core.update.reconcile import resolve

    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")
    replace(upstream, OPERATING, "She is curious.", "She is warm.")
    commit(upstream, "colliding")
    update(clone)

    repo = Repo(clone)
    outcome = resolve(clone, repo, OPERATING, "mine", repo.head())
    bases_now = state.load(clone)
    bases_now.set(OPERATING, outcome.base)
    state.save(clone, bases_now)

    replace(upstream, OPERATING, "Use the speak tool.", "Use the speak tool, briefly.")
    commit(upstream, "unrelated")
    report = update(clone)

    assert [o.state for o in report.prompts] == [MERGED]
    assert "She is sarcastic." in read(clone, OPERATING)
    assert "She is warm." not in read(clone, OPERATING), "the resolved change came back"


def test_resolving_refuses_an_unknown_choice(world):
    from src.core.update.reconcile import resolve

    _, clone = world
    with pytest.raises(ValueError):
        resolve(clone, Repo(clone), OPERATING, "whatever", "HEAD")


# --- what it refuses to do ----------------------------------------------------


def test_local_changes_to_the_engine_stop_the_update(world):
    upstream, clone = world
    write(clone, "src/core/brain.py", "print('my own patch')\n")
    replace(upstream, SOUL, "She is the one we ship.", "changed")
    commit(upstream, "anything")
    before = Repo(clone).head()

    report = update(clone)

    assert report.status == BLOCKED
    assert report.blocked_paths == ["src/core/brain.py"]
    assert Repo(clone).head() == before, "a blocked update still moved the repository"
    assert read(clone, "src/core/brain.py") == "print('my own patch')\n"


def test_a_diverged_checkout_is_reported_not_rewritten(world):
    upstream, clone = world
    write(clone, "data/prompts/mine.md", "a commit of my own\n")
    commit(clone, "local work")
    local_head = git(clone, "rev-parse", "HEAD")
    replace(upstream, SOUL, "She is the one we ship.", "changed")
    commit(upstream, "upstream work")

    report = update(clone)

    assert report.status == BLOCKED
    assert "fast-forward" in report.detail
    assert git(clone, "rev-parse", "HEAD") == local_head


def test_nothing_new_is_not_an_update(world):
    _, clone = world
    report = update(clone)

    assert report.status == CURRENT
    assert [s.status for s in report.steps if s.id == "apply"] == ["skipped"]


def test_a_directory_that_is_not_a_checkout_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_cached", None)
    report = runner.apply(root=tmp_path, source="test")

    assert report.status == BLOCKED
    assert "not a git checkout" in report.detail


def test_a_prompt_edited_mid_update_stops_the_run(world, monkeypatch):
    """The narrow window between reading the user's file and resetting it.

    The dashboard can save a prompt at any moment, including the moment after
    the updater has read it and before it hands the path to git. Losing that
    save is not acceptable, so the run re-reads and bails out instead.
    """
    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")
    replace(upstream, OPERATING, "Use the speak tool.", "Use the speak tool, briefly.")
    commit(upstream, "upstream work")
    before = Repo(clone).head()

    original_fetch = Repo.fetch

    def fetch_then_meddle(self, remote="origin"):
        original_fetch(self, remote)
        write(clone, OPERATING, read(clone, OPERATING) + "\na late save from the dashboard\n")

    monkeypatch.setattr(Repo, "fetch", fetch_then_meddle)
    report = update(clone)

    assert report.status == BLOCKED
    assert report.blocked_paths == [OPERATING]
    assert Repo(clone).head() == before
    assert "a late save from the dashboard" in read(clone, OPERATING)


def test_only_one_update_runs_at_a_time(world):
    _, clone = world
    with lock.held(clone, "somebody else"):
        report = update(clone)

    assert report.status == BLOCKED
    assert "already running" in report.headline


def test_a_stale_lock_does_not_wedge_the_feature_forever(world, monkeypatch):
    _, clone = world
    with lock.held(clone, "a process that died"):
        monkeypatch.setattr(lock, "STALE_AFTER", -1)
        report = update(clone)

    assert report.status == CURRENT, "a lock older than the timeout should have been cleared"


# --- when the file is gone upstream -------------------------------------------


def test_a_prompt_deleted_upstream_keeps_the_users_copy(world):
    upstream, clone = world
    replace(clone, SOUL, "She is the one we ship.", "She is mine.")
    (upstream / SOUL).unlink()
    commit(upstream, "drop the shipped soul")

    report = update(clone)

    assert [o.state for o in report.prompts] == [REMOVED]
    assert read(clone, SOUL) == "# Soul\n\nShe is mine.\n"


# --- degrading safely ----------------------------------------------------------


def test_a_first_update_takes_the_revision_they_are_on_as_the_base(world):
    """There is no state file before the first update, and none is needed.

    A checkout nobody has updated yet holds files that came out of the commit
    it is sitting on, so that commit is the base — by construction, not by
    guesswork. Refusing to merge here would make the very first update of every
    install a conflict.
    """
    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")
    replace(upstream, OPERATING, "Use the speak tool.", "Use the speak tool, briefly.")
    commit(upstream, "an easy change")
    assert not (clone / state.STATE_FILE).exists()

    report = update(clone)

    assert [o.state for o in report.prompts] == [MERGED]
    assert "She is sarcastic." in read(clone, OPERATING)
    assert "Use the speak tool, briefly." in read(clone, OPERATING)


def test_a_pending_conflict_outlives_a_lost_state_file(world):
    """The rule that makes the complexity affordable: it fails into the simple thing.

    Without the state file we do not know what their version was based on. The
    `.new` sitting on disk still says a conflict is open, so the merge is
    refused rather than guessed at from HEAD — which would read the changes
    they never took as deletions they made.
    """
    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")
    replace(upstream, OPERATING, "She is curious.", "She is warm.")
    commit(upstream, "colliding")
    update(clone)
    assert new_file_for(clone, OPERATING).exists()

    (clone / state.STATE_FILE).write_text("{ not json", encoding="utf-8")
    replace(upstream, OPERATING, "Use the speak tool.", "Use the speak tool, briefly.")
    commit(upstream, "an easy change nobody gets")
    report = update(clone)

    assert [o.state for o in report.prompts] == [CONFLICT]
    assert "no record of which version" in report.prompts[0].detail
    assert "She is sarcastic." in read(clone, OPERATING)


def test_an_unknown_state_format_is_ignored(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / state.STATE_FILE).write_text(json.dumps({"format": 99, "bases": {"a": "b"}}))

    assert state.load(tmp_path).bases == {}


def test_the_state_file_survives_a_round_trip(tmp_path):
    written = state.BaseMap({SOUL: "a" * 40})
    state.save(tmp_path, written)

    assert state.load(tmp_path).get(SOUL) == "a" * 40


def test_a_truncated_sha_is_not_a_base(tmp_path):
    assert state.BaseMap({SOUL: "abc"}).get(SOUL) is None


# --- backups and crashes -------------------------------------------------------


def test_the_users_prompt_is_in_the_backup_before_anything_is_touched(world):
    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")
    replace(upstream, OPERATING, "She is curious.", "She is warm.")
    commit(upstream, "colliding")

    report = update(clone)

    saved = clone / backup.BACKUP_ROOT / report.backup / OPERATING
    assert "She is sarcastic." in saved.read_text(encoding="utf-8")


def test_an_update_that_died_mid_flight_is_undone_by_the_next_one(world):
    upstream, clone = world
    write(clone, OPERATING, "the version I wrote\n")
    snapshot = backup.take(clone, [OPERATING], "deadbeef")
    backup.open_journal(clone, "merge", snapshot, "deadbeef", [OPERATING])
    # what a crash between the reset and the reconciliation leaves behind
    write(clone, OPERATING, "a half-applied upstream version\n")

    restored = backup.recover(clone)

    assert restored == [OPERATING]
    assert read(clone, OPERATING) == "the version I wrote\n"
    assert not (clone / backup.JOURNAL_FILE).exists()


def test_a_crash_before_anything_was_written_restores_nothing(world):
    _, clone = world
    snapshot = backup.take(clone, [OPERATING], "deadbeef")
    backup.open_journal(clone, "preflight", snapshot, "deadbeef", [OPERATING])
    write(clone, OPERATING, "untouched by the update\n")

    assert backup.recover(clone) == []
    assert read(clone, OPERATING) == "untouched by the update\n"
    assert not (clone / backup.JOURNAL_FILE).exists()


def test_old_backups_are_pruned(world, monkeypatch):
    _, clone = world
    monkeypatch.setattr(backup, "KEEP_BACKUPS", 2)
    for index in range(4):
        directory = clone / backup.BACKUP_ROOT / f"2024010{index}-000000"
        directory.mkdir(parents=True)
    backup.take(clone, [OPERATING], "deadbeef")

    kept = sorted(d.name for d in (clone / backup.BACKUP_ROOT).iterdir())
    assert len(kept) == 2


# --- the rebuild half ----------------------------------------------------------


def test_a_dependency_change_is_what_triggers_uv_sync(world):
    upstream, clone = world
    write(upstream, "uv.lock", "lock = 2\n")
    commit(upstream, "bump a dependency")

    calls = []
    report = runner.apply(
        root=clone, source="test",
        progress=lambda step: calls.append((step.id, step.status)),
    )

    dependencies = [s for s in report.steps if s.id == "dependencies"][0]
    assert dependencies.status != "skipped", "a lockfile change must not skip the sync"


def test_an_update_that_touches_nothing_buildable_skips_the_rebuild(world):
    upstream, clone = world
    replace(upstream, SOUL, "She is the one we ship.", "changed")
    commit(upstream, "prompt only")

    report = update(clone)

    statuses = {s.id: s.status for s in report.steps}
    assert statuses["dependencies"] == "skipped"
    assert statuses["dashboard"] == "skipped"
    assert "no dependency changes" in [s.detail for s in report.steps if s.id == "dependencies"][0]


def test_skipping_the_rebuild_is_reported_as_such(world):
    upstream, clone = world
    write(upstream, "uv.lock", "lock = 2\n")
    commit(upstream, "bump")

    report = update(clone, rebuild=False)

    assert {s.id: s.status for s in report.steps}["dependencies"] == "skipped"


# --- checking ------------------------------------------------------------------


def test_a_check_sees_what_is_waiting(world):
    upstream, clone = world
    replace(upstream, SOUL, "She is the one we ship.", "changed")
    commit(upstream, "something new")

    runner.invalidate()
    status = runner.check(root=clone, force=True)

    assert status.supported and status.available
    assert status.behind == 1
    assert status.commits[0]["subject"] == "something new"


def test_a_check_changes_nothing_in_the_working_copy(world):
    upstream, clone = world
    replace(clone, SOUL, "She is the one we ship.", "She is mine.")
    replace(upstream, SOUL, "She is the one we ship.", "theirs")
    commit(upstream, "upstream")
    before = Repo(clone).head()

    runner.invalidate()
    runner.check(root=clone, force=True)

    assert Repo(clone).head() == before
    assert read(clone, SOUL) == "# Soul\n\nShe is mine.\n"


def test_a_check_is_cached_between_calls(world, monkeypatch):
    _, clone = world
    runner.invalidate()
    runner.check(root=clone, force=True)

    def explode(self, remote="origin"):
        raise AssertionError("the cached check went back to the network")

    monkeypatch.setattr(Repo, "fetch", explode)
    assert runner.check(root=clone).supported


def test_a_check_reports_the_conflicts_waiting_for_a_decision(world):
    upstream, clone = world
    replace(clone, OPERATING, "She is curious.", "She is sarcastic.")
    replace(upstream, OPERATING, "She is curious.", "She is warm.")
    commit(upstream, "colliding")
    update(clone)

    runner.invalidate()
    assert runner.check(root=clone, force=True).reviews == [OPERATING]


def test_docker_is_told_to_rebuild_the_image(world, monkeypatch):
    _, clone = world
    monkeypatch.setattr(runner, "in_docker", lambda: True)
    runner.invalidate()

    status = runner.check(root=clone, force=True)
    assert not status.supported
    assert "Docker" in status.reason


# --- the javascript she has that is not the dashboard -------------------------


def test_an_update_to_the_discord_bot_installs_it(world, monkeypatch):
    """The bot was left out of the rebuild for as long as it existed.

    An update that changed its packages left the discord toggle on in the UI
    and the bot unable to start, saying so nowhere but its own stderr.
    """
    upstream, clone = world
    write(upstream, "src/core/skills/voice/bot/package.json", '{"name": "bea-discord-bot"}\n')
    commit(upstream, "bump the bot")

    ran = []

    def record(cwd, args):
        ran.append((cwd, args))
        return True, ""

    monkeypatch.setattr(runner.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(runner, "_command", record)

    report = update(clone)

    statuses = {s.id: s.status for s in report.steps}
    assert statuses["discord bot"] == "done"
    assert any("bot" in str(cwd) and args[:1] == ["npm"] for cwd, args in ran)


def test_the_bot_is_left_alone_when_it_did_not_change(world):
    upstream, clone = world
    replace(upstream, SOUL, "She is the one we ship.", "changed")
    commit(upstream, "prompt only")

    report = update(clone)

    assert {s.id: s.status for s in report.steps}["discord bot"] == "skipped"


def test_a_missing_npm_names_the_one_command_that_fixes_it(world, monkeypatch):
    upstream, clone = world
    write(upstream, "src/core/skills/voice/bot/package.json", '{"name": "bea-discord-bot"}\n')
    commit(upstream, "bump the bot")
    monkeypatch.setattr(runner.shutil, "which", lambda name: None if name == "npm" else "/usr/bin/x")

    report = update(clone)

    bot = [s for s in report.steps if s.id == "discord bot"][0]
    assert bot.status == "failed"
    assert "--install-node" in bot.detail


# --- the same file, written the way windows writes it -------------------------


def write_crlf(root: Path, relative: str, text: str) -> None:
    """A file as an editor on windows leaves it."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))


def test_a_prompt_stored_with_windows_line_endings_still_merges(world):
    """The three sides used to be read two different ways.

    The user's file came through python's text mode, which turns CRLF into LF;
    the other two came out of git as bytes, which does not. Every line then
    differed from itself, so a clean merge was reported as a collision and the
    engine's own improvements were dropped.
    """
    upstream, clone = world
    write_crlf(upstream, OPERATING, ORIGINAL)
    commit(upstream, "as windows wrote it")
    git(clone, "pull", "-q", "origin", "main")

    write_crlf(clone, OPERATING, ORIGINAL.replace("She is curious.", "She is sarcastic and tired."))
    write_crlf(upstream, OPERATING,
               ORIGINAL.replace("Use the speak tool.", "Use the speak tool, never narrate."))
    commit(upstream, "improve the manual")

    report = update(clone)

    merged = read(clone, OPERATING)
    assert "She is sarcastic and tired." in merged, "the user's character was dropped"
    assert "Use the speak tool, never narrate." in merged, "the engine improvement was dropped"
    assert [o.state for o in report.prompts] == [MERGED]


def test_an_identical_edit_is_not_a_conflict_because_of_line_endings(world):
    upstream, clone = world
    write_crlf(upstream, OPERATING, ORIGINAL)
    commit(upstream, "as windows wrote it")
    git(clone, "pull", "-q", "origin", "main")

    changed = ORIGINAL.replace("She is curious.", "She is curious and blunt.")
    write_crlf(clone, OPERATING, changed)
    write_crlf(upstream, OPERATING, changed)
    commit(upstream, "same change")

    assert [o.state for o in update(clone).prompts] == [UNTOUCHED]


def test_a_merge_hands_the_file_back_written_the_way_it_was_found(world):
    """Rewriting somebody's line endings behind their back is its own bug."""
    upstream, clone = world
    write_crlf(clone, OPERATING, ORIGINAL.replace("She is curious.", "She is sarcastic."))
    replace(upstream, OPERATING, "Use the speak tool.", "Use the speak tool, briefly.")
    commit(upstream, "an easy change")

    update(clone)

    raw = (clone / OPERATING).read_bytes()
    assert b"\r\n" in raw
    assert raw.count(b"\n") == raw.count(b"\r\n"), "half the file was converted"
