from mc_agent.core.agent import Agent
from mc_agent.core.config import Config
from mc_agent.utils.logger import setup_logger

def main():
    logger = setup_logger("Main")
    logger.info("=== BeaCraft Agent Middleware Starting ===")
    
    try:
        Config.validate()
        logger.info("Configuration validated.")
    except Exception as e:
        logger.critical(f"Configuration Error: {e}")
        return

    agent = Agent()
    agent.start()

if __name__ == "__main__":
    main()
