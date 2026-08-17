from sqlalchemy.orm import Session

from app.models import ChannelAccount, ChannelType, ContentVariant, Publication
from app.schemas import ChannelHealth
from app.services.adapters.base import (
    AdapterCapabilityError,
    AdapterLimits,
    AdapterResult,
    ChannelAdapter,
    ciphertext_health,
)
from app.services.metrics import empty_unavailable


class ManualCopyAdapter(ChannelAdapter):
    supports_autopost = False

    def __init__(self, channel_type: ChannelType) -> None:
        self.channel_type = channel_type

    def publish(
        self,
        db: Session,
        account: ChannelAccount,
        variant: ContentVariant,
        publication: Publication,
    ) -> AdapterResult:
        raise AdapterCapabilityError()

    def fetch_metrics(self, account: ChannelAccount, publication: Publication) -> dict:
        return empty_unavailable(reason="manual_copy_no_insights")

    def health(self, account: ChannelAccount) -> ChannelHealth:
        return ciphertext_health(account)

    def limits(self) -> AdapterLimits:
        requires_media = self.channel_type is ChannelType.instagram
        return AdapterLimits(max_text_len=2200, requires_media=requires_media)
