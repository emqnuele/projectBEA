"""A wait with a limit that never swallows the cancel of whoever is waiting.

Python 3.11's `asyncio.wait_for` did, when the awaited thing finished in the
same loop step as the cancel. Every test here holds on 3.11 and 3.12 alike.
"""

import asyncio
from pathlib import Path

import pytest

from src.utils.aio import wait_for

SRC = Path(__file__).resolve().parents[1] / "src"


async def test_a_cancel_that_lands_with_the_answer_still_cancels():
    ready = asyncio.Event()

    async def waiting():
        await wait_for(ready.wait(), 1.0)
        return "carried on"

    task = asyncio.create_task(waiting())
    await asyncio.sleep(0.01)
    ready.set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_the_answer_comes_back_when_it_arrives_in_time():
    async def answer():
        await asyncio.sleep(0.01)
        return 42

    assert await wait_for(answer(), 1.0) == 42


async def test_too_long_is_a_timeout():
    with pytest.raises(TimeoutError):
        await wait_for(asyncio.sleep(1.0), 0.01)


async def test_no_time_left_still_takes_an_answer_that_is_already_there():
    done = asyncio.get_running_loop().create_future()
    done.set_result("here")
    assert await wait_for(done, 0) == "here"


async def test_no_time_left_and_no_answer_is_a_timeout():
    with pytest.raises(TimeoutError):
        await wait_for(asyncio.sleep(1.0), 0)


async def test_no_limit_waits_for_the_answer():
    async def answer():
        await asyncio.sleep(0.01)
        return "late"

    assert await wait_for(answer(), None) == "late"


def test_nothing_in_src_waits_with_the_one_that_swallows_cancels():
    offenders = [f"{path.relative_to(SRC)}:{n}"
                 for path in SRC.rglob("*.py") if "node_modules" not in path.parts
                 for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if "asyncio.wait_for(" in line and path.name != "aio.py"]
    assert offenders == [], "use src.utils.aio.wait_for, which keeps the cancel on 3.11"
