"""Probe knowledge grounding for Nodex brand on VPS."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.db import get_session_factory
from app.models import BrandContentProfile, BrandProfile
from app.services.knowledge_grounding import ground_knowledge
from app.services.lightrag_client import get_lightrag_client


def main() -> None:
    db = get_session_factory()()
    try:
        brand = db.scalar(
            select(BrandProfile).where(
                BrandProfile.name == "Nodex",
                BrandProfile.deleted_at.is_(None),
            )
        )
        if brand is None:
            raise SystemExit("brand not found")
        profile = db.get(BrandContentProfile, brand.id)
        assert profile is not None
        query = (brand.niche or "").strip() or "вайбкодер бренд"
        raw = get_lightrag_client().query(query, mode="mix")
        result = ground_knowledge(profile, query, mode="mix")
        print(
            json.dumps(
                {
                    "filters": profile.knowledge_filters,
                    "mode": profile.knowledge_mode.value,
                    "query_head": query[:160],
                    "raw_ref_paths": [r.file_path for r in (raw.references or [])[:12]],
                    "raw_response_has_vibecoder": "VIBECODER" in (raw.response or ""),
                    "raw_response_has_brand_erp": "brand/ERP" in (raw.response or ""),
                    "raw_response_head": (raw.response or "")[:500],
                    "status": result.status.value,
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                    "ref_count": len(result.references),
                    "refs": [
                        {"id": r.id, "file_path": r.file_path} for r in result.references[:8]
                    ],
                    "context_head": (result.context or "")[:400],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
