import uvicorn
from src.web.app import app
import src.web.app as app_module

async def run_server(brain, host="0.0.0.0", port=8000):
    app_module.brain_instance = brain
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
