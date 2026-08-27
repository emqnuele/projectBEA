"""Walking out of a call, and the slow clock that lets her act on her own.

Sitting alone in an empty voice channel forever is the single most obviously
non-human thing a bot does. So is only ever acting the instant someone speaks.
"""

import pytest

from src.core.social.rhythm import RhythmTick


class Cfg:
    def __init__(self, **discord):
        self.skills = {"discord": {"enabled": True, **discord}}
        self.attention = {}


class Transport:
    """A discord bot that reports who is in each voice channel."""

    def __init__(self, members=()):
        self.members = list(members)
        self.joined = []
        self.left = 0

    async def list_voice_channels(self):
        return {"ok": True, "channels": [
            {"channelId": "vc1", "name": "general", "members": self.members},
        ]}

    async def join_voice(self, channel_id):
        self.joined.append(channel_id)
        return {"ok": True}

    async def leave_voice(self):
        self.left += 1
        return {"ok": True}


def surface(transport, **discord):
    from src.core.skills.voice.surface import VoiceSurface

    s = VoiceSurface(Cfg(**discord), bus=None, expression=None)
    s.initialize()
    s.transport = transport
    s.active = True
    return s


BEA = {"id": "bot", "name": "Bea"}
EMA = {"id": "1", "name": "Ema"}


# --- knowing where she is ----------------------------------------------------


async def test_she_remembers_which_call_she_joined():
    s = surface(Transport())
    await s._tool_join_voice("vc1")
    assert s.voice_channel == "vc1"


async def test_leaving_forgets_it():
    s = surface(Transport())
    await s._tool_join_voice("vc1")
    await s._tool_leave_voice()
    assert s.voice_channel is None


async def test_a_failed_join_is_not_remembered():
    class Broken(Transport):
        async def join_voice(self, channel_id):
            return {"ok": False, "error": "no permission"}

    s = surface(Broken())
    await s._tool_join_voice("vc1")
    assert s.voice_channel is None


# --- being left alone --------------------------------------------------------


async def test_she_stays_while_someone_is_with_her():
    transport = Transport(members=[BEA, EMA])
    s = surface(transport, auto_leave_seconds=60)
    await s._tool_join_voice("vc1")
    await s.check_solitude(now=0.0)
    await s.check_solitude(now=999.0)
    assert transport.left == 0


async def test_being_alone_briefly_is_not_enough_to_leave():
    transport = Transport(members=[BEA])
    s = surface(transport, auto_leave_seconds=60)
    await s._tool_join_voice("vc1")
    await s.check_solitude(now=0.0)
    await s.check_solitude(now=30.0)
    assert transport.left == 0


async def test_she_leaves_a_call_everyone_walked_out_of():
    transport = Transport(members=[BEA])
    s = surface(transport, auto_leave_seconds=60)
    await s._tool_join_voice("vc1")
    await s.check_solitude(now=0.0)
    await s.check_solitude(now=61.0)
    assert transport.left == 1
    assert s.voice_channel is None


async def test_someone_coming_back_resets_the_clock():
    transport = Transport(members=[BEA])
    s = surface(transport, auto_leave_seconds=60)
    await s._tool_join_voice("vc1")
    await s.check_solitude(now=0.0)
    transport.members = [BEA, EMA]
    await s.check_solitude(now=50.0)
    transport.members = [BEA]
    await s.check_solitude(now=55.0)
    await s.check_solitude(now=100.0)
    assert transport.left == 0


async def test_auto_leave_can_be_switched_off():
    transport = Transport(members=[BEA])
    s = surface(transport, auto_leave_seconds=0)
    await s._tool_join_voice("vc1")
    await s.check_solitude(now=0.0)
    await s.check_solitude(now=99999.0)
    assert transport.left == 0


async def test_a_call_she_is_not_in_is_none_of_her_business():
    transport = Transport(members=[BEA])
    s = surface(transport, auto_leave_seconds=60)
    await s.check_solitude(now=0.0)
    await s.check_solitude(now=999.0)
    assert transport.left == 0


async def test_a_channel_that_vanished_is_forgotten_not_retried():
    class Gone(Transport):
        async def list_voice_channels(self):
            return {"ok": True, "channels": []}

    s = surface(Gone(), auto_leave_seconds=60)
    await s._tool_join_voice("vc1")
    await s.check_solitude(now=0.0)
    assert s.voice_channel is None


# --- the slow clock ----------------------------------------------------------


class Counter:
    def __init__(self, result=0, fail: bool = False):
        self.runs = 0
        self.result = result
        self.fail = fail

    async def run_once(self):
        self.runs += 1
        if self.fail:
            raise RuntimeError("boom")
        return self.result


async def test_a_tick_runs_everything_it_owns():
    spontaneous, agenda = Counter(1), Counter(2)
    tick = RhythmTick(spontaneous=spontaneous, agenda=agenda)
    assert await tick.run_once() == 3
    assert (spontaneous.runs, agenda.runs) == (1, 1)


async def test_one_broken_pass_does_not_stop_the_other():
    spontaneous, agenda = Counter(fail=True), Counter(2)
    tick = RhythmTick(spontaneous=spontaneous, agenda=agenda)
    assert await tick.run_once() == 2
    assert agenda.runs == 1


async def test_a_tick_with_nothing_wired_does_nothing():
    assert await RhythmTick().run_once() == 0


async def test_the_kept_intentions_run_before_the_idle_chatter():
    """Having a reason beats having a gap: she should not fill the silence with
    small talk and then find she also meant to say something."""
    order = []

    class Ordered(Counter):
        def __init__(self, label):
            super().__init__()
            self.label = label

        async def run_once(self):
            order.append(self.label)
            return 0

    await RhythmTick(spontaneous=Ordered("spontaneous"), agenda=Ordered("agenda")).run_once()
    assert order == ["agenda", "spontaneous"]


# --- the brain builds it -----------------------------------------------------


def test_presence_is_one_of_the_skills_the_brain_builds():
    from src.core.brain import SKILL_CLASSES
    from src.core.skills.presence.surface import PresenceSkill

    assert PresenceSkill in SKILL_CLASSES


@pytest.mark.parametrize("key", ["auto_leave_seconds", "access_mode"])
def test_the_new_discord_knobs_are_in_the_schema(key):
    from src.core.settings_schema import section

    assert key in {f.key for f in section("discord").settings}


# --- leaving because she wants to --------------------------------------------


def _tools(s):
    return {t.name for t in s.tools()}


def test_she_is_not_offered_a_door_she_is_not_standing_at():
    """An absent tool is a stronger constraint than a rule in the prompt."""
    s = surface(Transport())
    assert "discord_leave_voice" not in _tools(s)


async def test_once_in_a_call_she_can_walk_out_of_it():
    s = surface(Transport())
    await s._tool_join_voice("vc1")
    assert "discord_leave_voice" in _tools(s)


async def test_leaving_is_a_decision_she_can_explain():
    transport = Transport()
    s = surface(transport)
    await s._tool_join_voice("vc1")
    answer = await s._tool_leave_voice(reason="mi sono annoiata")
    assert transport.left == 1
    assert "mi sono annoiata" in answer


async def test_she_can_leave_without_saying_why():
    s = surface(Transport())
    await s._tool_join_voice("vc1")
    assert "FAILED" not in await s._tool_leave_voice()


async def test_why_she_left_reaches_the_dashboard():
    published = []

    class Events:
        def publish(self, category, source, message, metadata=None):
            published.append((source, message, metadata or {}))

    s = surface(Transport())
    s.events = Events()
    await s._tool_join_voice("vc1")
    await s._tool_leave_voice(reason="vado a dormire")
    assert published
    assert "vado a dormire" in published[0][1]


async def test_a_refused_leave_does_not_pretend_she_left():
    class Stuck(Transport):
        async def leave_voice(self):
            return {"ok": False, "error": "not connected"}

    s = surface(Stuck())
    await s._tool_join_voice("vc1")
    assert (await s._tool_leave_voice()).startswith("FAILED")
    assert s.voice_channel == "vc1"


async def test_leaving_on_her_own_still_forgets_the_call():
    s = surface(Transport())
    await s._tool_join_voice("vc1")
    await s._tool_leave_voice(reason="basta")
    assert s.voice_channel is None
    assert "discord_leave_voice" not in _tools(s)


# --- and being told she may ---------------------------------------------------


def test_the_prompt_tells_her_she_can_leave():
    s = surface(Transport())
    s.voice_channel = "vc1"
    assert "discord_leave_voice" in s.context_section


def test_the_prompt_does_not_dangle_it_when_she_is_not_in_a_call():
    assert "discord_leave_voice" not in surface(Transport()).context_section


def test_the_prompt_says_leaving_is_hers_to_decide():
    s = surface(Transport())
    s.voice_channel = "vc1"
    section = s.context_section.lower()
    assert "leave" in section
    assert "ask" in section or "permission" in section or "nobody" in section
