from uuid import UUID

from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import BrandContentProfile, KnowledgeMode, User
from app.schemas import BrandContentProfileUpdate
from app.security import utc_now
from app.services.brand_service import MUTATE_BRAND_ROLES, require_brand
from app.config import get_settings
from app.services.content_profile_presets import CONTENT_PROFILE_PRESETS
from app.services.platform_policy import merge_v1_policies, NODEX_PLATFORM_POLICIES_V1


def _empty_profile(brand_id: UUID) -> BrandContentProfile:
    return BrandContentProfile(
        brand_id=brand_id,
        positioning="",
        audience_segments=[],
        audience_pains=[],
        content_pillars=[],
        proof_facts=[],
        preferred_cta_styles=[],
        banned_openers=[],
        structure_rules="",
        platform_policies={},
        platform_policies_v1=None,
        platform_policies_version=0,
        knowledge_mode=KnowledgeMode.off,
        knowledge_filters=[],
        require_human_approval=True,
    )


def ensure_content_profile(db: Session, brand_id: UUID) -> BrandContentProfile:
    profile = db.get(BrandContentProfile, brand_id)
    if profile is not None:
        return profile
    profile = _empty_profile(brand_id)
    db.add(profile)
    db.flush()
    return profile


def get_or_create_content_profile(
    db: Session, user: User, brand_id: UUID
) -> BrandContentProfile:
    brand, _membership = require_brand(db, user, brand_id)
    return ensure_content_profile(db, brand.id)


def update_content_profile(
    db: Session,
    user: User,
    brand_id: UUID,
    payload: BrandContentProfileUpdate,
) -> BrandContentProfile:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    profile = ensure_content_profile(db, brand.id)
    data = payload.model_dump(exclude_unset=True)
    v1_updates = data.pop("platform_policies_v1", None)
    for field, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        elif isinstance(value, list):
            value = list(value)
        elif isinstance(value, dict):
            value = dict(value)
        setattr(profile, field, value)
    if v1_updates is not None:
        profile.platform_policies_v1 = merge_v1_policies(profile.platform_policies_v1, v1_updates)
        profile.platform_policies_version = (profile.platform_policies_version or 0) + 1
    profile.updated_at = utc_now()
    db.flush()
    return profile


def apply_content_profile_preset(
    db: Session, user: User, brand_id: UUID, preset_id: str
) -> BrandContentProfile:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    preset = CONTENT_PROFILE_PRESETS.get(preset_id)
    if preset is None:
        raise AppError(404, "not_found", "Пресет не найден")
    profile = ensure_content_profile(db, brand.id)
    for field, value in preset.items():
        if field == "platform_policies_v1":
            continue
        if isinstance(value, list):
            value = list(value)
        elif isinstance(value, dict):
            value = dict(value)
        setattr(profile, field, value)
    if preset_id == "nodex" or preset_id == "alexander_personal":
        if get_settings().platform_policy_v1_enabled:
            profile.platform_policies_v1 = dict(NODEX_PLATFORM_POLICIES_V1)
            profile.platform_policies_version = (profile.platform_policies_version or 0) + 1
    profile.updated_at = utc_now()
    db.flush()
    return profile
