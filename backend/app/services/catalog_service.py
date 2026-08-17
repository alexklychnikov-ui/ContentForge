from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import extract, or_, select
from sqlalchemy.orm import Session

from app.catalogs.ru_holidays import SEED_YEARS, holidays_for_year
from app.models import Holiday, HolidaySource


def ensure_system_holidays(db: Session, year: int) -> None:
    existing_dates = set(
        db.scalars(
            select(Holiday.date).where(
                Holiday.source == HolidaySource.system,
                Holiday.country == "RU",
                extract("year", Holiday.date) == year,
            )
        ).all()
    )
    for holiday_date, name in holidays_for_year(year):
        if holiday_date in existing_dates:
            continue
        db.add(
            Holiday(
                id=uuid4(),
                date=holiday_date,
                name=name,
                country="RU",
                source=HolidaySource.system,
                brand_id=None,
            )
        )
    db.flush()


def seed_default_years(db: Session) -> None:
    for year in SEED_YEARS:
        ensure_system_holidays(db, year)


def list_holidays(
    db: Session,
    year: int,
    month: int | None,
    brand_id: UUID | None,
) -> list[Holiday]:
    ensure_system_holidays(db, year)
    filters = [
        Holiday.country == "RU",
        extract("year", Holiday.date) == year,
    ]
    if brand_id is None:
        filters.append(Holiday.source == HolidaySource.system)
    else:
        filters.append(
            or_(Holiday.source == HolidaySource.system, Holiday.brand_id == brand_id)
        )
    if month is not None:
        filters.append(extract("month", Holiday.date) == month)
    return list(
        db.scalars(select(Holiday).where(*filters).order_by(Holiday.date, Holiday.name)).all()
    )


def parse_year_month(year: int | None, month: int | None) -> tuple[int, int | None]:
    today = date.today()
    resolved_year = year if year is not None else today.year
    return resolved_year, month
