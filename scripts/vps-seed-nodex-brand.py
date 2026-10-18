"""Seed / refresh Nodex workspace brand with Alexander ERP freelance kit."""
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
        "Microsoft Dynamics AX 2012 (X++): доработки розничного ERP-контура "
        "до проводки и обмена — цены, склад/Infor, касса УКМ-4, 1С, Rabbit, "
        "ЕГАИС, Ветис, Честный знак. Python/AI — ускоритель того же контура."
    ),
    "audience": (
        "Ритейл и сети на AX 2012, внутренние IT и интеграторы розницы, "
        "владельцы процессов цены/склада/кассы/регуляторики — "
        "нужна доработка до проводки и обмена, а не до прототипа экрана"
    ),
    "voice_tone": (
        "Прямой, экспертный, без нейрошаблонов и hard sell. "
        "Язык контура: цена → ценник → касса; склад → обмен; документ → проводка. "
        "Конкретная сцена из практики → как закрыл стык → уносимый ход. "
        "Спокойная уверенность практика, не «гуру цифровизации»."
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
        "Доработки Dynamics AX 2012 (X++) по розничному контуру",
        "Цена / акция / лояльность / ценник / выгрузка в кассу УКМ-4",
        "Складской учёт и обмен с Infor / WMS",
        "Интеграции: 1С, RabbitMQ, казначейские платежи",
        "Регуляторика: ЕГАИС, Ветис, Честный знак",
        "Разбор стыков и сопровождение уже живых контуров",
        "Python/AI для ускорения разбора и автоматизации вокруг ERP",
    ],
    "example_posts": [
        (
            "Цена «есть в AX» — ещё не значит, что касса продаёт ту же.\n\n"
            "На ценнике дисконтная карта, в акции смена ценовой группы, "
            "в УКМ уехала минимальная цена. Расхождение ловится до продажи, "
            "а не по инвентаризации.\n\n"
            "Ход на 48 часов: пройти один SKU от торгового соглашения "
            "до строки на кассе и отметить, где обрывается цепочка.\n\n"
            "1) Чинить экран цены\n2) Чинить стык AX → ценник → УКМ\nЧто выбираете?"
        ),
        (
            "Интеграция без журнала — это не обмен, а надежда.\n\n"
            "В рабочем контуре Rabbit/1С/Infor живут статус, повтор и ошибки за день. "
            "«Отправили и забыли» разваливается на частичной отгрузке "
            "или когда маркировка не дошла до кассы.\n\n"
            "Уносимый ход: для одного потока выписать "
            "исходящее → журнал → входящее → что считается успехом.\n\n"
            "Спорно: без идемпотентности любой «успешный» пост в очередь — лотерея."
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
