from app.models import KnowledgeMode

ALEXANDER_PERSONAL_PRESET: dict = {
    "positioning": (
        "Python/AI, Telegram-боты, автоматизация, ERP/Dynamics AX; "
        "понял бизнес-задачу → быстро собрал рабочее решение → довёл до деплоя"
    ),
    "audience_segments": [
        "малый бизнес",
        "самозанятые",
        "компании без IT",
        "ранние стартапы",
    ],
    "audience_pains": [
        "размытое ТЗ",
        "автоматизация хаоса",
        "бот без процесса",
        "нет IT-команды",
    ],
    "content_pillars": [
        "практика/ошибка+фикс",
        "автоматизация МСБ",
        "AI как инструмент",
        "ERP→MVP",
    ],
    "proof_facts": [],
    "preferred_cta_styles": [
        "выбор 1/2",
        "спорный тезис",
    ],
    "banned_openers": [
        "В современном мире",
        "Сегодня поговорим",
        "Хотите узнать секрет",
    ],
    "structure_rules": (
        "боль → сцена → личная практика → уносимый ход → CTA; "
        "лид 1–2 ударные строки; без hard sell; не выдумывать кейсы/цифры"
    ),
    "platform_policies": {
        "tenchat": "короткий пост; без hard sell; личная практика и уносимый ход",
    },
    "knowledge_mode": KnowledgeMode.required,
    "knowledge_filters": [],
    "require_human_approval": True,
}

CONTENT_PROFILE_PRESETS: dict[str, dict] = {
    "alexander_personal": ALEXANDER_PERSONAL_PRESET,
}
