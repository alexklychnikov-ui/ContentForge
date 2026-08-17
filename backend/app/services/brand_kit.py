from app.errors import AppError
from app.models import BrandProfile
from app.security import utc_now


def is_brand_kit_complete(brand: BrandProfile) -> bool:
    required = (
        brand.name,
        brand.niche,
        brand.audience,
        brand.voice_tone,
        brand.timezone,
        brand.default_locale,
    )
    if any(not str(value).strip() for value in required):
        return False
    return bool(brand.offers)


def sync_onboarding_timestamp(brand: BrandProfile) -> None:
    if is_brand_kit_complete(brand):
        if brand.onboarding_completed_at is None:
            brand.onboarding_completed_at = utc_now()
        return
    brand.onboarding_completed_at = None


def assert_can_generate_plan(brand: BrandProfile) -> None:
    if not is_brand_kit_complete(brand) or brand.onboarding_completed_at is None:
        raise AppError(
            409,
            "brand_kit_incomplete",
            "Сначала заполните Brand Kit",
        )
