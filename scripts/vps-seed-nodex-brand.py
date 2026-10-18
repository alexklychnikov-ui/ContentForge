"""Move/create Nodex under the real admin workspace."""
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
        "Python/AI-разработка и автоматизация для малого бизнеса: "
        "Telegram-боты, интеграции, ERP/Dynamics AX → рабочие MVP под задачу"
    ),
    "audience": (
        "Малый бизнес и самозанятые (заказы в Telegram/WhatsApp), "
        "компании без штатного IT, основатели ранних стартапов, "
        "которым нужно быстро собрать рабочее решение и довести до деплоя"
    ),
    "voice_tone": (
        "Прямой, экспертный, без нейрошаблонов и hard sell. "
        "Говорю языком пользы и операционки МСБ: конкретная сцена → "
        "как снял боль → уносимый ход. Спокойная уверенность практика."
    ),
    "stopwords": [
        "в современном мире",
        "сегодня поговорим",
        "хотите узнать секрет",
        "гарантирую результат",
        "лучшие на рынке",
        "уникальное предложение",
        "нейросеть изменит всё",
    ],
    "offers": [
        "Telegram-боты и автоматизация рутины под бизнес-процесс",
        "AI-интеграции (OpenAI, базы знаний / RAG) в рабочие workflow",
        "Быстрый MVP: от бизнес-задачи до деплоя",
        "Автоматизация и интеграции вокруг ERP / Dynamics AX",
        "Сопровождение и доработка уже запущенных ботов/скриптов",
    ],
    "example_posts": [
        (
            "Размытое ТЗ — не проблема клиента. Проблема — когда берёшь его в работу "
            "как есть.\n\nНа последнем боте сначала зафиксировал один сценарий: "
            "заказ → статус → уведомление. Остальное — во вторую очередь.\n\n"
            "Ход на 48 часов: выписать 3 шага процесса до первой строчки кода.\n\n"
            "1) Сначала процесс\n2) Сначала «универсальный» бот\nЧто выбираете?"
        ),
        (
            "AI не чинит хаос. Он его ускоряет — если под ним нет процесса.\n\n"
            "Собрал связку: знания в LightRAG → ответ в рабочем чате. "
            "Помогло только после того, как отфильтровали, что вообще можно "
            "спрашивать.\n\nУносимый ход: один источник правды + один канал ответа.\n\n"
            "Спорно: без регламента AI — дорогой генератор шума."
        ),
    ],
    "default_locale": Locale.ru,
    "timezone": "Asia/Irkutsk",
}

PROOF_FACTS = [
    "Стек: Python, AI/OpenAI, Telegram-боты, автоматизация, ERP/Dynamics AX",
    "Формула: понял бизнес-задачу → быстро собрал рабочее решение → довёл до деплоя",
    "Опыт: LightRAG (база знаний + Docker/облако), expense-bot с AI-отчётами, мониторинг цен с уведомлениями в Telegram",
    "ЦА: МСБ, самозанятые, компании без IT, ранние стартапы",
]


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
        setattr(profile, key, value)
    profile.proof_facts = list(PROOF_FACTS)
    profile.knowledge_mode = KnowledgeMode.required
    profile.require_human_approval = True
    profile.platform_policies = {
        "tenchat": "короткий пост; без hard sell; личная практика и уносимый ход",
        "telegram": "короче TenChat-формата ок; один CTA; без воды",
        "vk": "можно чуть развернуть сцену; без корпоративного пафоса",
        "instagram": "лид в первые 2 строки; сцена + практика; CTA выбором 1/2",
    }
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

        # Soft-delete mistaken Nodex on smoke workspaces
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
                    "knowledge_mode": profile.knowledge_mode.value,
                    "require_human_approval": profile.require_human_approval,
                    "timezone": brand.timezone,
                    "offers": brand.offers,
                    "proof_facts": profile.proof_facts,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
