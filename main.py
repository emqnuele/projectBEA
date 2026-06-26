#!/usr/bin/env python
# thin wrapper so `python main.py` keeps working; real entrypoint lives in src.cli
from src.cli import run

if __name__ == "__main__":
    run()
