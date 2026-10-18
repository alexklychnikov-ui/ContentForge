"""Seed / refresh Nodex workspace brand with vibe-coder (ERP-background) kit."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.db import get_session_factory
from app.models import BrandProfile, KnowledgeMode, Locale, Membership, User, Workspace
from app.security import utc_now
from app.services.brand_kit import sync_onboarding_timestamp
from app.services.content_profile_presets import ALEXANDER_PERSONAL_PRESET
from app.services.content_profile_service import ensure_content_profile
from app.services.platform_policy import NODEX_PLATFORM_POLICIES_V1

BRAND_NAME = "Nodex"
OWNER_EMAIL = "admin@testfullcrm.alexklyvibe.ru"

BRAND_KIT = {
    "niche": (
        "Python / AI / Telegram-боты / автоматизация и интеграции через vibe coding "
        "(AI-assisted development). Узнаваемость — ERP-бэкграунд (Dynamics AX): "
        "доводить до рабочего результата, а не продавать доработку AX."
    ),
    "audience": (
        "Малый бизнес и самозанятые с заказами в мессенджерах, "
        "основатели и операционка без штатного IT, "
        "заказчики ботов, AI-автоматизации и интеграций, "
        "которым нужен рабочий контур до деплоя, а не прототип"
    ),
    "voice_tone": (
        "Прямой, экспертный, без нейрошаблонов и hard sell. "
        "Сцена из вайбкодинга / бота / автоматизации → практика → уносимый ход. "
        "ERP — опциональная одна фраза бэкграунда (стыки, журнал, «до деплоя»), "
        "не заголовок и не каталог AX-классов."
    ),
    "stopwords": [
        "в современном мире",
        "сегодня поговорим",
        "хотите узнать секрет",
        "гарантирую результат",
        "лучшие на рынке",
        "уникальное предложение",
        "нейросеть изменит всё",
        "в эру цифровизации",
    ],
    "offers": [
        "Telegram-боты под бизнес-процесс: заявки, FAQ, статусы, CRM, уведомления",
        "AI + автоматизация: документы, Excel, классификация, RAG / базы знаний",
        "Интеграции и внутренние сервисы: API, FastAPI, PostgreSQL, связки систем",
        "Vibe coding / AI-assisted: быстрая сборка MVP до деплоя и инструкции",
        "Сопровождение и доработка уже запущенных ботов и автоматизаций",
    ],
    "example_posts": [
        (
            "Размытое ТЗ на бота — не проблема клиента. Проблема — когда берёшь его в работу "
            "как есть.\n\nСначала один сценарий: заказ → статус → уведомление. "
            "Остальное — во вторую очередь.\n\n"
            "В корпоративных контурах так же: сначала стык, который должен сойтись.\n\n"
            "Ход на 48 часов: выписать 3 шага процесса до первой строчки кода.\n\n"
            "1) Сначала процесс\n2) Сначала «универсальный» бот\nЧто выбираете?"
        ),
        (
            "AI не чинит хаос. Он его ускоряет — если под ним нет процесса.\n\n"
            "Собрал связку: знания в LightRAG → ответ в рабочем чате. "
            "Помогло только после того, как отфильтровали, что вообще можно спрашивать.\n\n"
            "Уносимый ход: один источник правды + один канал ответа.\n\n"
            "Спорно: вайбкодинг без критерия «готово» — дорогой генератор шума."
        ),
    ],
    "default_locale": Locale.ru,
    "timezone": "Asia/Irkutsk",
}


def _apply_kit(brand: BrandProfile) -> None:
    brand.name = BRAND_NAME
    brand.niche = BRAND_KIT["niche"]
    brand.audience = BRAND_KIT["audience"]
    brand.voice_tone = BRAND_KIT["voice_tone"]
    brand.stopwords = list(BRAND_KIT["stopwords"])
    brand.offers = list(BRAND_KIT["offers"])
    brand.example_posts = list(BRAND_KIT["example_posts"])
    brand.default_locale = BRAND_KIT["default_locale"]
    brand.timezone = BRAND_KIT["timezone"]
    brand.auto_pipeline_enabled = False
    brand.auto_pipeline_lead_hours = 24
    brand.default_slot_hour = 12
    sync_onboarding_timestamp(brand)


def _apply_profile(profile) -> None:
    for key, value in ALEXANDER_PERSONAL_PRESET.items():
        if isinstance(value, list):
            setattr(profile, key, list(value))
        elif isinstance(value, dict):
            setattr(profile, key, dict(value))
        else:
            setattr(profile, key, value)
    profile.knowledge_mode = KnowledgeMode.required
    profile.require_human_approval = True
    profile.platform_policies_v1 = dict(NODEX_PLATFORM_POLICIES_V1)
    profile.platform_policies_version = (profile.platform_policies_version or 0) + 1
    profile.updated_at = utc_now()


def main() -> None:
    db = get_session_factory()()
    try:
        user = db.scalar(select(User).where(User.email == OWNER_EMAIL))
        if user is None:
            raise SystemExit(f"owner not found: {OWNER_EMAIL}")
        membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
        if membership is None:
            raise SystemExit("no membership")
        ws = db.get(Workspace, membership.workspace_id)
        assert ws is not None

        mistaken = list(
            db.scalars(
                select(BrandProfile).where(
                    BrandProfile.name == BRAND_NAME,
                    BrandProfile.workspace_id != ws.id,
                    BrandProfile.deleted_at.is_(None),
                )
            )
        )
        for row in mistaken:
            row.deleted_at = utc_now()

        brand = db.scalar(
            select(BrandProfile).where(
                BrandProfile.workspace_id == ws.id,
                BrandProfile.name == BRAND_NAME,
                BrandProfile.deleted_at.is_(None),
            )
        )
        created = False
        if brand is None:
            brand = BrandProfile(workspace_id=ws.id, name=BRAND_NAME)
            db.add(brand)
            created = True

        _apply_kit(brand)
        db.flush()
        profile = ensure_content_profile(db, brand.id)
        _apply_profile(profile)
        db.commit()

        print(
            json.dumps(
                {
                    "created": created,
                    "soft_deleted_mistaken": [str(r.id) for r in mistaken],
                    "brand_id": str(brand.id),
                    "name": brand.name,
                    "owner": user.email,
                    "workspace": ws.name,
                    "workspace_id": str(ws.id),
                    "niche": brand.niche,
                    "positioning": profile.positioning,
                    "audience_segments": profile.audience_segments,
                    "audience_pains": profile.audience_pains,
                    "content_pillars": profile.content_pillars,
                    "proof_facts": profile.proof_facts,
                    "knowledge_filters": profile.knowledge_filters,
                    "knowledge_mode": profile.knowledge_mode.value,
                    "require_human_approval": profile.require_human_approval,
                    "timezone": brand.timezone,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
