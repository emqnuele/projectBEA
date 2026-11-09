"""`wait_for` as Python 3.12 has it, on 3.11 too.

On 3.11 `asyncio.wait_for` returns the result when the thing it waits on
finishes in the same loop step as a cancel of the caller, and the cancel is
gone: a turn that was called off goes on. 3.12 rebuilt it on `asyncio.timeout`
and keeps the cancel. This is that version, so both behave the same way.
"""

import asyncio
from typing import Awaitable, Optional, TypeVar

T = TypeVar("T")


async def wait_for(aw: Awaitable[T], timeout: Optional[float]) -> T:
    """The result of `aw`, or `TimeoutError` after `timeout` seconds; None waits for ever."""
    if timeout is not None and timeout <= 0:
        # this path is the same code on 3.11 and 3.12
        return await asyncio.wait_for(aw, timeout)
    async with asyncio.timeout(timeout):
        return await aw


__all__ = ["wait_for"]
