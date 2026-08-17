from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import ChannelAccount, ChannelStatus, ContentVariant, Publication
from app.schemas import ChannelHealth


class AdapterError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = True) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


class AdapterCapabilityError(AdapterError):
    def __init__(
        self,
        message: str = "Автопост для этого канала недоступен, скопируйте текст вручную",
    ) -> None:
        super().__init__("manual_copy_required", message, retryable=False)


@dataclass(frozen=True)
class AdapterResult:
    external_id: str
    external_url: str | None = None
    meta: dict | None = None


@dataclass(frozen=True)
class AdapterLimits:
    max_text_len: int = 4096
    requires_media: bool = False


def redact_secret(text: str, secret: str | None) -> str:
    if not text:
        return text
    cleaned = text
    if secret:
        variants = {secret, secret.replace(" ", "")}
        for item in variants:
            if item:
                cleaned = cleaned.replace(item, "***")
    return cleaned


def ciphertext_health(account: ChannelAccount) -> ChannelHealth:
    if account.status == ChannelStatus.revoked or account.revoked_at is not None:
        return ChannelHealth(id=account.id, status=ChannelStatus.revoked, ok=False)
    if account.token_ciphertext:
        return ChannelHealth(id=account.id, status=ChannelStatus.connected, ok=True)
    return ChannelHealth(id=account.id, status=ChannelStatus.error, ok=False)


class ChannelAdapter(ABC):
    supports_autopost: bool = False

    @abstractmethod
    def publish(
        self,
        db: Session,
        account: ChannelAccount,
        variant: ContentVariant,
        publication: Publication,
    ) -> AdapterResult:
        raise NotImplementedError

    @abstractmethod
    def fetch_metrics(self, account: ChannelAccount, publication: Publication) -> dict:
        raise NotImplementedError

    @abstractmethod
    def health(self, account: ChannelAccount) -> ChannelHealth:
        raise NotImplementedError

    @abstractmethod
    def limits(self) -> AdapterLimits:
        raise NotImplementedError
