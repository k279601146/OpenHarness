"""QQ channel implementation using botpy SDK."""

import asyncio
import logging
import os
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING


from openharness.channels.bus.events import OutboundMessage
from openharness.channels.bus.queue import MessageBus
from openharness.channels.impl.base import BaseChannel
from openharness.config.schema import QQConfig

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[5]
WEB_PUBLIC_DIR = PROJECT_ROOT / "apps" / "web" / "public"

try:
    import botpy
    from botpy.message import C2CMessage

    QQ_AVAILABLE = True
except ImportError:
    QQ_AVAILABLE = False
    botpy = None
    C2CMessage = None

if TYPE_CHECKING:
    from botpy.message import C2CMessage


def _make_bot_class(channel: "QQChannel") -> "type[botpy.Client]":
    """Create a botpy Client subclass bound to the given channel."""
    intents = botpy.Intents(public_messages=True, direct_message=True)

    class _Bot(botpy.Client):
        def __init__(self):
            # Disable botpy's file log — not using loguru; default "botpy.log" fails on read-only fs
            super().__init__(intents=intents, ext_handlers=False)

        async def on_ready(self):
            logger.info("QQ bot ready: %s", self.robot.name)

        async def on_c2c_message_create(self, message: "C2CMessage"):
            await channel._on_message(message)

        async def on_direct_message_create(self, message):
            await channel._on_message(message)

    return _Bot


class QQChannel(BaseChannel):
    """QQ channel using botpy SDK with WebSocket connection."""

    name = "qq"

    def __init__(self, config: QQConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: QQConfig = config
        self._client: "botpy.Client | None" = None
        self._processed_ids: deque = deque(maxlen=1000)
        self._msg_seq: int = 1  # 消息序列号，避免被 QQ API 去重

    async def start(self) -> None:
        """Start the QQ bot."""
        if not QQ_AVAILABLE:
            logger.error("QQ SDK not installed. Run: pip install qq-botpy")
            return

        secret = getattr(self.config, "secret", None) or getattr(self.config, "app_secret", "")
        if not self.config.app_id or not secret:
            logger.error("QQ app_id and secret not configured")
            return

        self._running = True
        BotClass = _make_bot_class(self)
        self._client = BotClass()

        logger.info("QQ bot started (C2C private message)")
        await self._run_bot()

    async def _run_bot(self) -> None:
        """Run the bot connection with auto-reconnect."""
        while self._running:
            try:
                secret = getattr(self.config, "secret", None) or getattr(self.config, "app_secret", "")
                await self._client.start(appid=self.config.app_id, secret=secret)
            except Exception as e:
                logger.warning("QQ bot error: %s", e)
            if self._running:
                logger.info("Reconnecting QQ bot in 5 seconds...")
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the QQ bot."""
        self._running = False
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
        logger.info("QQ bot stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through QQ."""
        if not self._client:
            logger.warning("QQ client not initialized")
            return
        try:
            msg_id = msg.metadata.get("message_id")
            if msg.content and msg.content.strip():
                self._msg_seq += 1  # 递增序列号
                await self._client.api.post_c2c_message(
                    openid=msg.chat_id,
                    msg_type=0,
                    content=msg.content,
                    msg_id=msg_id,
                    msg_seq=self._msg_seq,  # 添加序列号避免去重
                )

            for media_ref in msg.media:
                media_url = self._resolve_media_url(media_ref)
                if not media_url:
                    logger.warning("QQ media requires a public URL, skipped: %s", media_ref)
                    continue
                uploaded = await self._client.api.post_c2c_file(
                    openid=msg.chat_id,
                    file_type=1,
                    url=media_url,
                    srv_send_msg=False,
                )
                self._msg_seq += 1
                await self._client.api.post_c2c_message(
                    openid=msg.chat_id,
                    msg_type=7,
                    media=uploaded,
                    msg_id=msg_id,
                    msg_seq=self._msg_seq,
                )
        except Exception as e:
            logger.error("Error sending QQ message: %s", e)

    def _resolve_media_url(self, media_ref: str) -> str | None:
        if not media_ref:
            return None
        if media_ref.startswith(("http://", "https://")):
            return media_ref

        public_base_url = os.getenv("EXTERNAL_CHANNEL_PUBLIC_BASE_URL", "").strip().rstrip("/")
        if not public_base_url:
            return None

        try:
            path = Path(media_ref).resolve()
            public_root = WEB_PUBLIC_DIR.resolve()
            if path.is_file() and path.is_relative_to(public_root):
                rel_url = path.relative_to(public_root).as_posix()
                return f"{public_base_url}/{rel_url}"
        except Exception:
            return None
        return None

    async def _on_message(self, data: "C2CMessage") -> None:
        """Handle incoming message from QQ."""
        try:
            # Dedup by message ID
            if data.id in self._processed_ids:
                return
            self._processed_ids.append(data.id)

            author = data.author
            user_id = str(getattr(author, 'id', None) or getattr(author, 'user_openid', 'unknown'))
            content = (data.content or "").strip()
            if not content:
                return

            await self._handle_message(
                sender_id=user_id,
                chat_id=user_id,
                content=content,
                metadata={"message_id": data.id},
            )
        except Exception:
            logger.exception("Error handling QQ message")
