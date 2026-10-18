from app.services.content_quality import store_approval_on_payload
from app.services.variant_checksum import (
    approval_matches,
    clear_text_approval,
    payload_checksum,
    store_checksum_meta,
)


def test_checksum_ignores_meta_and_changes_with_text():
    a = store_checksum_meta({"text": "hello", "_meta": {"quality": {"blockers": []}}})
    b = store_checksum_meta({"text": "hello", "_meta": {"approved_at": "x"}})
    assert payload_checksum(a) == payload_checksum(b)
    c = store_checksum_meta({"text": "hello!"})
    assert payload_checksum(c) != payload_checksum(a)


def test_approval_bound_to_revision_and_checksum():
    payload = store_checksum_meta({"text": "x", "headline": "h"})
    checksum = payload["_meta"]["payload_checksum"]
    payload = store_approval_on_payload(
        payload,
        approved_at="t",
        approved_by="u",
        revision=3,
        checksum=checksum,
    )
    assert approval_matches(3, payload)
    assert not approval_matches(4, payload)
    payload = clear_text_approval(payload)
    assert not approval_matches(3, payload)
