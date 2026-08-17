import { useMemo, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import type { BrandPublic, PlanItemPublic } from "../api/types";
import { EmptyState, ErrorBanner } from "../components/Status";
import { MonthGrid } from "../components/MonthGrid";
import { CHANNEL_LABELS, CONTENT_LABELS, MVP_CHANNELS, label } from "../labels";

type Shell = { brand: BrandPublic | null };

export function CalendarPage() {
  const { brand } = useOutletContext<Shell>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [channel, setChannel] = useState("all");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [theme, setTheme] = useState("Тема слота");

  const plansQuery = useQuery({
    queryKey: ["plans", brand?.id, year, month],
    queryFn: () => cf.plans(brand!.id, year, month),
    enabled: Boolean(brand),
  });
  const plan = plansQuery.data?.find((row) => row.status !== "archived") ?? plansQuery.data?.[0];
  const items = useMemo(() => {
    const all = plan?.items ?? [];
    if (channel === "all") return all;
    return all.filter((item) => item.channel_type === channel);
  }, [plan, channel]);
  const dayItems = items.filter((item) => item.date === selectedDate);

  const addItem = useMutation({
    mutationFn: () =>
      cf.addPlanItem(plan!.id, {
        date: selectedDate,
        channel_type: channel === "all" ? "telegram" : channel,
        content_type: "social_post",
        theme,
        goal: "awareness",
        hook: "",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["plans"] }),
  });

  const openPiece = useMutation({
    mutationFn: async (item: PlanItemPublic) => {
      if (item.content_piece_id) {
        return item.content_piece_id;
      }
      const piece = await cf.createPiece(brand!.id, {
        type: item.content_type,
        plan_item_id: item.id,
      });
      return piece.id;
    },
    onSuccess: (pieceId) => navigate(`/content/${pieceId}`),
  });

  if (!brand) {
    return (
      <main className="page">
        <EmptyState title="Нет бренда" hint="Сначала онбординг." cta="Онбординг" to="/onboarding" />
      </main>
    );
  }

  return (
    <main className="page grid">
      <h1>Календарь</h1>
      <p className="muted">Клик по дню открывает слоты. Перетаскивание отключено.</p>
      <ErrorBanner error={plansQuery.error || addItem.error || openPiece.error} />
      <div className="row">
        <label className="field">
          Год
          <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
        </label>
        <label className="field">
          Месяц
          <input type="number" min={1} max={12} value={month} onChange={(e) => setMonth(Number(e.target.value))} />
        </label>
        <label className="field">
          Канал
          <select value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="all">все</option>
            {MVP_CHANNELS.map((type) => (
              <option key={type} value={type}>
                {label(CHANNEL_LABELS, type)}
              </option>
            ))}
          </select>
        </label>
        <Link className="btn" to="/plan">
          Мастер плана
        </Link>
      </div>
      <div className="row muted">
        <span className="chip">черновик</span>
        <span className="chip">очередь</span>
        <span className="chip">опубликован</span>
      </div>
      {!plan ? (
        <EmptyState title="Нет плана на месяц" hint="Сгенерируйте слоты в мастере." cta="Сгенерировать план" to="/plan" />
      ) : (
        <div className="split">
          <MonthGrid
            year={year}
            month={month}
            items={items}
            selectedDate={selectedDate}
            onSelectDate={setSelectedDate}
          />
          <aside className="panel">
            <h3>{selectedDate ? `Слоты ${selectedDate}` : "Выберите день"}</h3>
            {dayItems.length === 0 ? <p className="muted">Пустой день.</p> : null}
            {dayItems.map((item) => (
              <div key={item.id} className="card">
                <div>
                  {label(CHANNEL_LABELS, item.channel_type)} · {label(CONTENT_LABELS, item.content_type)}
                </div>
                <strong>{item.theme}</strong>
                <p className="muted">{item.hook}</p>
                <button className="btn" type="button" onClick={() => openPiece.mutate(item)}>
                  Открыть редактор
                </button>
              </div>
            ))}
            {plan.status === "draft" && selectedDate ? (
              <div className="grid">
                <label className="field">
                  Тема
                  <input value={theme} onChange={(e) => setTheme(e.target.value)} />
                </label>
                <button className="btn secondary" type="button" onClick={() => addItem.mutate()}>
                  Создать слот
                </button>
              </div>
            ) : null}
          </aside>
        </div>
      )}
    </main>
  );
}
