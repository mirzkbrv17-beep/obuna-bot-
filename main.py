import asyncio
import logging

from bot import run
from config import load_config


def main() -> None:
    cfg = load_config()
    logging.basicConfig(level=cfg.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run(cfg))


if __name__ == "__main__":
    main()
