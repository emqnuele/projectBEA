import uvicorn

import src.web.app as app_module
from src.utils.logger import get_logger
from src.web.app import app

logger = get_logger("bea.web.server")


async def run_server(brain, host: str = "127.0.0.1", port: int = 8000):
    """Serves the dashboard + brain API.

    Binds to loopback by default: no endpoint is authenticated, so exposing the
    port on the LAN hands over full control of Bea. `--host 0.0.0.0` is a
    deliberate opt-in.
    """
    app_module.brain_instance = brain
    if host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(f"Binding on {host}: the brain API has no authentication.")
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
