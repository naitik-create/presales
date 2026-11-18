"""Job worker. Run one process per WORKER_COUNT: python worker.py"""
import logging

from app.config import get_settings
from app.core.jobs import work_forever

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    get_settings()
    work_forever()
