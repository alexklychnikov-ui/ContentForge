import { useMemo } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { cf } from "../api/cf";
import type { BrandPublic } from "../api/types";
import { EmptyState, ErrorBanner, JobBanner } from "../components/Status";
import { MonthGrid } from "../components/MonthGrid";
import { getSession, listRecentJobs } from "../auth/session";
import { label, PUB_STATUS } from "../labels";

type Shell = { brand: BrandPublic | null; brands: BrandPublic[]; brandsLoading: boolean };

export function DashboardPage() {
  const { brand, brands, brandsLoading } = useOutletContext<Shell>();
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  const plansQuery = useQuery({
    queryKey: ["plans", brand?.id, year, month],
    queryFn: () => cf.plans(brand!.id, year, month),
    enabled: Boolean(brand),
  });
  const pubsQuery = useQuery({
    queryKey: ["publications", brand?.id],
    queryFn: () => cf.publications(brand!.id),
    enabled: Boolean(brand),
  });
  const jobsQuery = useQuery({
    queryKey: ["recent-jobs", listRecentJobs().map((j) => j.id).join(",")],
    queryFn: async () => {
      const jobs = listRecentJobs();
      return Promise.all(jobs.map((item) => cf.job(item.id).catch(() => null)));
    },
    enabled: Boolean(getSession()),
    refetchInterval: 2000,
  });

  const plan = plansQuery.data?.[0];
  const items = plan?.items ?? [];
  const pubs = pubsQuery.data ?? [];
  const weekAhead = Date.now() + 7 * 24 * 3600 * 1000;
  const upcoming = pubs
    .filter((row) => {
      const ts = new Date(row.scheduled_at).getTime();
      return ts >= Date.now() && ts <= weekAhead;
    })
    .slice(0, 7);
  const kpis = useMemo(
    () => ({
      slots: items.length,
      published: pubs.filter((row) => row.status === "published" || row.status === "published_manual").length,
      failed: pubs.filter((row) => row.status === "failed" || row.status === "dead").length,
      drafts: pubs.filter((row) => row.status === "draft").length,
    }),
    [items.length, pubs],
  );

  if (brandsLoading) {
    return (
      <main className="page">
        <p className="muted">Загрузка…</p>
      </main>
    );
  }
  if (!brand) {
    return (
      <main className="page">
        <EmptyState
          title="Нет бренда"
          hint="Сначала заполните Brand Kit — без него план не генерируется."
          cta="Открыть онбординг"
          to="/onboarding"
        />
      </main>
    );
  }

  return (
    <main className="page grid">
      <h1>Дашборд · {brand.name}</h1>
      {!brand.onboarding_completed ? (
        <EmptyState
          title="Brand Kit не завершён"
          hint="Генерация плана недоступна, пока нет офферов и профиля."
          cta="Дополнить профиль"
          to="/onboarding"
        />
      ) : null}
      <ErrorBanner error={plansQuery.error || pubsQuery.error} />
      <div className="cards">
        <div className="card">
          <div className="muted">Слоты месяца</div>
          <h2>{kpis.slots}</h2>
        </div>
        <div className="card">
          <div className="muted">Опубликовано</div>
          <h2>{kpis.published}</h2>
        </div>
        <div className="card">
          <div className="muted">Ошибки</div>
          <h2>{kpis.failed}</h2>
        </div>
        <div className="card">
          <div className="muted">Черновики публикаций</div>
          <h2>{kpis.drafts}</h2>
        </div>
      </div>
      <div className="row">
        <Link className="btn" to="/plan">
          Сгенерировать план
        </Link>
        <Link className="btn secondary" to="/queue">
          Открыть очередь
        </Link>
      </div>
      {(jobsQuery.data ?? []).filter(Boolean).map((job) =>
        job ? (
          <JobBanner key={job.id} status={job.status} error={job.error} label={`Джоба ${job.type}`} />
        ) : null,
      )}
      <div className="split">
        <div className="panel">
          <h3>Мини-календарь</h3>
          {items.length === 0 ? (
            <EmptyState title="Нет слотов" hint="Соберите план на месяц." cta="Мастер плана" to="/plan" />
          ) : (
            <MonthGrid year={year} month={month} items={items} selectedDate={null} onSelectDate={() => undefined} />
          )}
        </div>
        <div className="panel">
          <h3>Ближайшие 7 дней</h3>
          {upcoming.length === 0 ? (
            <p className="muted">Нет запланированных публикаций.</p>
          ) : (
            <ul>
              {upcoming.map((row) => (
                <li key={row.id}>
                  {new Date(row.scheduled_at).toLocaleString("ru")} · {label(PUB_STATUS, row.status)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      {brands.length > 1 ? <p className="muted">Активный бренд переключается в шапке.</p> : null}
    </main>
  );
}
