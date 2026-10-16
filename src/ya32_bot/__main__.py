"""``python -m ya32_bot`` — run the bot."""

import asyncio

from ya32_bot.app import run

if __name__ == "__main__":
    asyncio.run(run())
