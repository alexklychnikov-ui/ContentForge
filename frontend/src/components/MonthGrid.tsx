import type { PlanItemPublic } from "../api/types";
import { CHANNEL_LABELS, label } from "../labels";

const DOW = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

type Props = {
  year: number;
  month: number;
  items: PlanItemPublic[];
  selectedDate: string | null;
  onSelectDate: (iso: string) => void;
};

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function isoDate(year: number, month: number, day: number): string {
  return `${year}-${pad(month)}-${pad(day)}`;
}

export function MonthGrid({ year, month, items, selectedDate, onSelectDate }: Props) {
  const first = new Date(year, month - 1, 1);
  const startOffset = (first.getDay() + 6) % 7;
  const daysInMonth = new Date(year, month, 0).getDate();
  const cells: { iso: string; day: number; inMonth: boolean }[] = [];
  for (let i = 0; i < startOffset; i += 1) {
    cells.push({ iso: `pad-${i}`, day: 0, inMonth: false });
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push({ iso: isoDate(year, month, day), day, inMonth: true });
  }
  while (cells.length % 7 !== 0) {
    cells.push({ iso: `tail-${cells.length}`, day: 0, inMonth: false });
  }

  const byDate = new Map<string, PlanItemPublic[]>();
  for (const item of items) {
    const list = byDate.get(item.date) ?? [];
    list.push(item);
    byDate.set(item.date, list);
  }

  return (
    <div className="month-grid" data-testid="month-grid">
      {DOW.map((name) => (
        <div className="dow" key={name}>
          {name}
        </div>
      ))}
      {cells.map((cell) => {
        if (!cell.inMonth) {
          return <div key={cell.iso} className="day-cell muted" />;
        }
        const dayItems = byDate.get(cell.iso) ?? [];
        const selected = selectedDate === cell.iso;
        return (
          <button
            key={cell.iso}
            type="button"
            className={`day-cell${selected ? " selected" : ""}`}
            onClick={() => onSelectDate(cell.iso)}
            draggable={false}
            data-date={cell.iso}
          >
            <strong>{cell.day}</strong>
            <div>
              {dayItems.slice(0, 3).map((item) => (
                <span className="chip" key={item.id}>
                  {label(CHANNEL_LABELS, item.channel_type)}
                </span>
              ))}
              {dayItems.length > 3 ? <span className="chip">+{dayItems.length - 3}</span> : null}
            </div>
          </button>
        );
      })}
    </div>
  );
}
