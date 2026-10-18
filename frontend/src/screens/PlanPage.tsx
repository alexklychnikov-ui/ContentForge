import { useEffect, useMemo, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import { ApiError } from "../api/client";
import type { BrandPublic, JobPublic, PlanPublic } from "../api/types";
import { useActionFeedback } from "../components/ActionFeedback";
import { EmptyState, ErrorBanner } from "../components/Status";
import { CHANNEL_LABELS, CONTENT_LABELS, MVP_CHANNELS, PLAN_STATUS, label } from "../labels";

type Shell = { brand: BrandPublic | null };

function isActiveChannel(status: string, revokedAt: string | null | undefined): boolean {
  if (revokedAt) return false;
  return status !== "revoked";
}

export function PlanPage() {
  const { brand } = useOutletContext<Shell>();
  const queryClient = useQueryClient();
  const { trackAction, trackJob } = useActionFeedback();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [channels, setChannels] = useState<string[]>([]);
  const [targets, setTargets] = useState({ social_post: 8, article: 0 });
  const [job, setJob] = useState<JobPublic | null>(null);
  const [plan, setPlan] = useState<PlanPublic | null>(null);

  const channelsQuery = useQuery({
    queryKey: ["channels", brand?.id],
    queryFn: () => cf.channels(brand!.id),
    enabled: Boolean(brand),
  });
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

  const connectedChannelTypes = useMemo(() => {
    const active = new Set(
      (channelsQuery.data ?? [])
        .filter((row) => isActiveChannel(row.status, row.revoked_at))
        .map((row) => row.type),
    );
    return MVP_CHANNELS.filter((type) => active.has(type));
  }, [channelsQuery.data]);

  useEffect(() => {
    setChannels((prev) => {
      const kept = prev.filter((type) => connectedChannelTypes.includes(type as (typeof MVP_CHANNELS)[number]));
      if (kept.length > 0) return kept;
      return connectedChannelTypes.length > 0 ? [connectedChannelTypes[0]] : [];
    });
  }, [brand?.id, connectedChannelTypes]);

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
      const labelText = confirm ? "Перегенерация плана" : "Генерация плана";
      const done = await trackJob(
        labelText,
        async () => {
          try {
            return await cf.generatePlan(brand!.id, {
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
          } catch (error) {
            if (error instanceof ApiError && error.code === "plan_active_exists") {
              const existingId = error.details.job_id;
              if (typeof existingId === "string" && existingId) {
                return { job_id: existingId };
              }
            }
            throw error;
          }
        },
        { kind: "generate_plan", maxTicks: 90 },
      );
      const status =
        done.status === "queued" ||
        done.status === "running" ||
        done.status === "succeeded" ||
        done.status === "failed"
          ? done.status
          : "failed";
      setJob({
        id: "done",
        type: "generate_plan",
        status,
        result: done.result ?? null,
        error: done.error,
        created_at: new Date().toISOString(),
      });
      if (done.status === "succeeded" && done.result?.plan_id) {
        const loaded = await cf.getPlan(String(done.result.plan_id));
        setPlan(loaded);
        await queryClient.invalidateQueries({ queryKey: ["plans"] });
      }
      return done;
    },
  });

  const approve = useMutation({
    mutationFn: () =>
      trackAction("Утверждение плана", () => cf.patchPlan(plan!.id, { status: "approved" })),
    onSuccess: (row) => setPlan(row),
  });

  const busy = generate.isPending;

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
      <ErrorBanner
        error={generate.error || approve.error || holidaysQuery.error || channelsQuery.error}
      />
      {job?.status === "failed" ? <ErrorBanner error={new Error(job.error || "Ошибка генерации")} /> : null}
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
          {channelsQuery.isLoading ? (
            <p className="muted">Загрузка каналов…</p>
          ) : connectedChannelTypes.length === 0 ? (
            <p className="muted">
              Нет подключённых каналов.{" "}
              <Link to="/channels">Подключить в Каналах</Link>
            </p>
          ) : (
            connectedChannelTypes.map((type) => (
              <label key={type}>
                <input
                  type="checkbox"
                  checked={channels.includes(type)}
                  disabled={busy}
                  onChange={(e) =>
                    setChannels((prev) =>
                      e.target.checked
                        ? [...prev, type]
                        : prev.filter((item) => item !== type),
                    )
                  }
                />{" "}
                {label(CHANNEL_LABELS, type)}
              </label>
            ))
          )}
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
          Показаны только каналы, подключённые к текущему бренду. Для старта: один канал + Пост (8).
          «Сгенерировать» добавляет/заменяет слоты только по выбранным каналам в текущем плане;
          «Перегенерировать» — полная перезапись.
          Для текущего месяца слоты ставятся с сегодняшней даты (таймзона бренда), не с 1-го числа.
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
