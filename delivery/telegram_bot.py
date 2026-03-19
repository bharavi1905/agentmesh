import asyncio
import logging

from telegram import Bot
from telegram.error import TelegramError

from utils import config

logger = logging.getLogger(__name__)


async def _send(bot_token: str, chat_id: str, message: str) -> None:
    async with Bot(token=bot_token) as bot:
        await bot.send_message(chat_id=chat_id, text=message)


def send_telegram_alert(message: str) -> str:
    """Send a stock market alert to the configured Telegram chat.

    Checks DRY_RUN first — if true, logs the message and returns 'dry_run'
    without hitting the Telegram API.

    Returns 'sent' on success, 'dry_run' in dry-run mode.
    Raises on unrecoverable error.
    """
    if config.DRY_RUN:
        logger.info("[DRY RUN] Alert suppressed — would have sent:\n%s", message)
        print(f"\n[DRY RUN] Alert suppressed — would have sent:\n{message}\n")
        return "dry_run"

    logger.info("Sending Telegram alert to chat %s", config.TELEGRAM_CHAT_ID)
    try:
        asyncio.run(_send(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, message))
        logger.info("Telegram alert sent successfully")
        return "sent"
    except TelegramError as exc:
        logger.error("Failed to send Telegram alert: %s", exc)
        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    result = send_telegram_alert("agentmesh test alert — session 2 complete")
    print(f"Result: {result}")
