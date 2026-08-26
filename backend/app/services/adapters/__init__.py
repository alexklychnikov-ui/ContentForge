from typing import assert_never

from app.models import ChannelType
from app.services.adapters.base import ChannelAdapter
from app.services.adapters.gmail import GmailAdapter
from app.services.adapters.manual import ManualCopyAdapter
from app.services.adapters.telegram import TelegramAdapter
from app.services.adapters.vk import VkAdapter

_TELEGRAM = TelegramAdapter()
_VK = VkAdapter()
_IG = ManualCopyAdapter(ChannelType.instagram)
_WP = ManualCopyAdapter(ChannelType.wordpress)
_GMAIL = GmailAdapter()


def get_adapter(channel_type: ChannelType) -> ChannelAdapter:
    if channel_type is ChannelType.telegram:
        return _TELEGRAM
    if channel_type is ChannelType.vk:
        return _VK
    if channel_type is ChannelType.instagram:
        return _IG
    if channel_type is ChannelType.wordpress:
        return _WP
    if channel_type is ChannelType.gmail:
        return _GMAIL
    assert_never(channel_type)
