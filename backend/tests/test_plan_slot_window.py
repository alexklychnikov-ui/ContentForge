from datetime import date

from app.services.ai_jobs import plan_slot_window


def test_current_month_starts_today() -> None:
    start, end = plan_slot_window(2026, 10, today=date(2026, 10, 18))
    assert start == date(2026, 10, 18)
    assert end == date(2026, 10, 31)


def test_future_month_starts_first() -> None:
    start, end = plan_slot_window(2026, 11, today=date(2026, 10, 18))
    assert start == date(2026, 11, 1)
    assert end == date(2026, 11, 30)


def test_past_month_full_window() -> None:
    start, end = plan_slot_window(2026, 9, today=date(2026, 10, 18))
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_first_day_of_month() -> None:
    start, end = plan_slot_window(2026, 10, today=date(2026, 10, 1))
    assert start == date(2026, 10, 1)
    assert end == date(2026, 10, 31)
