from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/api/v1/health")
def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "features": {
            "platform_policy_v1": settings.platform_policy_v1_enabled,
            "central_publication_gate": settings.central_publication_gate_enabled,
            "cover_generation": settings.cover_generation_enabled,
        },
    }
