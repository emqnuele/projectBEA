from contextlib import asynccontextmanager

import uvicorn

from src.utils.logger import get_logger
from src.web.app import app
from src.web.deps import set_brain

logger = get_logger("bea.web.server")

# how long uvicorn waits for open connections (the dashboard's event streams)
# before it stops waiting and goes on with the shutdown. There used to be no
# bound at all: ctrl+c with the dashboard open never got past "Waiting for
# connections to close" until the tab was closed by hand.
GRACEFUL_TIMEOUT = 5.0


async def run_server(brain, host: str = "127.0.0.1", port: int = 8000,
                     on_shutdown=None, graceful_timeout: float = GRACEFUL_TIMEOUT):
    """Serves the dashboard + brain API.

    Binds to loopback by default: no endpoint is authenticated, so exposing the
    port on the LAN hands over full control of Bea. `--host 0.0.0.0` is a
    deliberate opt-in.

    `on_shutdown` runs while the server is shutting down rather than after it:
    the skills (the discord supervisor especially) have to go down together
    with the server, not once it has already gone.
    """
    set_brain(brain)
    if host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(f"Binding on {host}: the brain API has no authentication.")

    @asynccontextmanager
    async def lifespan(_app):
        yield
        if on_shutdown is not None:
            await on_shutdown()

    # the app object is shared (the tests stand doubles in behind it), so the
    # lifespan only lives for this serve and is put back afterwards
    previous = app.router.lifespan_context
    app.router.lifespan_context = lifespan
    try:
        config = uvicorn.Config(app, host=host, port=port, log_level="info",
                                timeout_graceful_shutdown=graceful_timeout)
        server = uvicorn.Server(config)
        await server.serve()
    finally:
        app.router.lifespan_context = previous
