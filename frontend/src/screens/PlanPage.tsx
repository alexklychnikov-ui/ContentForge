import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import { ApiError, pollJob } from "../api/client";
import type { BrandPublic, JobPublic, PlanPublic } from "../api/types";
import { pushRecentJob } from "../auth/session";
import { EmptyState, ErrorBanner, JobBanner } from "../components/Status";
import { CHANNEL_LABELS, CONTENT_LABELS, MVP_CHANNELS, PLAN_STATUS, label } from "../labels";

type Shell = { brand: BrandPublic | null };

async function waitForPlanJob(jobId: string, setJob: (job: JobPublic) => void): Promise<JobPublic> {
  pushRecentJob({ id: jobId, type: "generate_plan", at: new Date().toISOString() });
  setJob({
    id: jobId,
    type: "generate_plan",
    status: "running",
    result: null,
    error: null,
    created_at: new Date().toISOString(),
  });
  return pollJob(jobId, (id) => cf.job(id), { intervalMs: 700, maxTicks: 90 });
}

export function PlanPage() {
  const { brand } = useOutletContext<Shell>();
  const queryClient = useQueryClient();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [channels, setChannels] = useState<string[]>(["telegram"]);
  const [targets, setTargets] = useState({ social_post: 8, article: 0, email: 0 });
  const [job, setJob] = useState<JobPublic | null>(null);
  const [plan, setPlan] = useState<PlanPublic | null>(null);

  const holidaysQuery = useQuery({
    queryKey: ["holidays", year, month, brand?.id],
    queryFn: () => cf.holidays(year, month, brand?.id),
    enabled: Boolean(brand),
  });
  const trendsQuery = useQuery({
    queryKey: ["trends", brand?.id],
    queryFn: () => cf.trends(brand!.id),
    enabled: Boolean(brand),
  });
  const plansQuery = useQuery({
    queryKey: ["plans", brand?.id, year, month],
    queryFn: () => cf.plans(brand!.id, year, month),
    enabled: Boolean(brand),
  });

  const generate = useMutation({
    mutationFn: async (confirm: boolean) => {
      const cleanTargets = Object.fromEntries(
        Object.entries(targets).filter(([, value]) => Number(value) > 0),
      );
      if (Object.keys(cleanTargets).length === 0) {
        throw new Error("Укажите хотя бы одну частоту > 0 (обычно Пост).");
      }
      if (channels.length === 0) {
        throw new Error("Выберите хотя бы один канал.");
      }
      setJob({
        id: "pending",
        type: "generate_plan",
        status: "queued",
        result: null,
        error: null,
        created_at: new Date().toISOString(),
      });
      let jobId: string;
      try {
        const accepted = await cf.generatePlan(brand!.id, {
          year,
          month,
          channels,
          targets: cleanTargets,
          locale: brand?.default_locale ?? "ru",
          include_holidays: true,
          include_trends: true,
          confirm,
          create_revision: confirm && plansQuery.data?.some((row) => row.status === "approved"),
        });
        jobId = accepted.job_id;
      } catch (error) {
        if (error instanceof ApiError && error.code === "plan_active_exists") {
          const existingId = error.details.job_id;
          if (typeof existingId === "string" && existingId) {
            jobId = existingId;
          } else {
            setJob(null);
            throw error;
          }
        } else {
          setJob(null);
          throw error;
        }
      }
      const done = await waitForPlanJob(jobId, setJob);
      setJob(done);
      if (done.status === "succeeded" && done.result?.plan_id) {
        const loaded = await cf.getPlan(String(done.result.plan_id));
        setPlan(loaded);
        await queryClient.invalidateQueries({ queryKey: ["plans"] });
      }
      if (done.status === "failed") {
        throw new Error(done.error || "Генерация плана: ошибка");
      }
      return done;
    },
  });

  const approve = useMutation({
    mutationFn: () => cf.patchPlan(plan!.id, { status: "approved" }),
    onSuccess: (row) => setPlan(row),
  });

  const busy = generate.isPending || job?.status === "queued" || job?.status === "running";

  if (!brand) {
    return (
      <main className="page">
        <EmptyState title="Нет бренда" hint="Сначала Brand Kit." cta="Онбординг" to="/onboarding" />
      </main>
    );
  }
  if (!brand.onboarding_completed) {
    return (
      <main className="page">
        <EmptyState
          title="План недоступен"
          hint="Без завершённого Brand Kit generate вернёт brand_kit_incomplete."
          cta="Заполнить Brand Kit"
          to="/onboarding"
        />
      </main>
    );
  }

  const shown = plan ?? plansQuery.data?.find((row) => row.status !== "archived") ?? null;
  const holidays = holidaysQuery.data ?? [];
  const trends = (trendsQuery.data ?? []).filter((row) => row.status === "active");

  return (
    <main className="page grid">
      <h1>Мастер плана</h1>
      <ErrorBanner error={generate.error || approve.error || holidaysQuery.error} />
      <JobBanner status={busy ? job?.status || "running" : job?.status} error={job?.error} label="Генерация плана" />
      {busy ? (
        <p className="muted" role="status">
          Ждём ответ AI (обычно 5–30 с). Кнопки заблокированы — не обновляй страницу.
        </p>
      ) : null}
      <div className="panel grid">
        <div className="row">
          <label className="field">
            Год
            <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} disabled={busy} />
          </label>
          <label className="field">
            Месяц
            <input
              type="number"
              min={1}
              max={12}
              value={month}
              onChange={(e) => setMonth(Number(e.target.value))}
              disabled={busy}
            />
          </label>
        </div>
        <div className="row">
          {MVP_CHANNELS.map((type) => (
            <label key={type}>
              <input
                type="checkbox"
                checked={channels.includes(type)}
                disabled={busy}
                onChange={(e) =>
                  setChannels((prev) => {
                    const next = e.target.checked
                      ? [...prev, type]
                      : prev.filter((item) => item !== type);
                    if (type === "gmail") {
                      setTargets((t) => ({
                        ...t,
                        email: e.target.checked ? Math.max(t.email, 2) : 0,
                      }));
                    }
                    return next;
                  })
                }
              />{" "}
              {label(CHANNEL_LABELS, type)}
            </label>
          ))}
        </div>
        <div className="row">
          {Object.entries(targets).map(([key, value]) => (
            <label className="field" key={key}>
              {label(CONTENT_LABELS, key)}
              <input
                type="number"
                min={0}
                value={value}
                disabled={busy}
                onChange={(e) => setTargets((prev) => ({ ...prev, [key]: Number(e.target.value) }))}
              />
            </label>
          ))}
        </div>
        <p className="muted">
          Для старта: только Telegram + Пост (8). Статья/письмо поднимают сложность генерации;
          письмо имеет смысл при включённом Gmail. Если черновик уже есть — «Перегенерировать».
        </p>
        <div>
          <h3>Праздники</h3>
          {holidaysQuery.isLoading ? (
            <p className="muted">Загрузка праздников…</p>
          ) : holidays.length === 0 ? (
            <p className="muted">Праздников в этом месяце нет.</p>
          ) : (
            <ul>
              {holidays.map((item) => (
                <li key={item.id}>
                  {item.date}: {item.name}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3>Тренды</h3>
          {trends.length === 0 ? <p className="muted">Тренды не заданы</p> : null}
          {trends.map((item) => (
            <div key={item.id}>
              {item.title} — {item.note}
            </div>
          ))}
        </div>
        <div className="row">
          <button className="btn" type="button" disabled={busy} onClick={() => generate.mutate(false)}>
            {busy ? "Генерация…" : "Сгенерировать"}
          </button>
          <button
            className="btn secondary"
            type="button"
            disabled={busy}
            onClick={() => {
              if (window.confirm("Черновики слотов перезапишутся, утверждённые публикации — нет. Продолжить?")) {
                generate.mutate(true);
              }
            }}
          >
            {busy ? "Ждём…" : "Перегенерировать"}
          </button>
          {shown?.status === "draft" ? (
            <button
              className="btn"
              type="button"
              disabled={busy}
              onClick={() => {
                setPlan(shown);
                approve.mutate();
              }}
            >
              Утвердить план
            </button>
          ) : null}
        </div>
      </div>
      {busy && !shown ? (
        <div className="empty">
          <h3>Идёт генерация</h3>
          <p>Слоты появятся здесь, когда job завершится (succeeded).</p>
        </div>
      ) : shown ? (
        <div className="panel">
          <h3>
            Слоты · {label(PLAN_STATUS, shown.status)} · {shown.items.length}
          </h3>
          <table>
            <thead>
              <tr>
                <th>Дата</th>
                <th>Канал</th>
                <th>Тип</th>
                <th>Тема</th>
              </tr>
            </thead>
            <tbody>
              {shown.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.date}</td>
                  <td>{label(CHANNEL_LABELS, item.channel_type)}</td>
                  <td>{label(CONTENT_LABELS, item.content_type)}</td>
                  <td>{item.theme}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="Плана ещё нет" hint="Задайте частоты и нажмите «Сгенерировать»." cta="Дашборд" to="/" />
      )}
    </main>
  );
}
