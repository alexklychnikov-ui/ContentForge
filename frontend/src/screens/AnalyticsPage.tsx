import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { cf } from "../api/cf";
import type { BrandPublic } from "../api/types";
import { EmptyState, ErrorBanner } from "../components/Status";
import { CHANNEL_LABELS, label } from "../labels";

type Shell = { brand: BrandPublic | null };

function dayRange(days: number): { from: string; to: string } {
  const to = new Date();
  const from = new Date(Date.now() - days * 24 * 3600 * 1000);
  return { from: from.toISOString(), to: to.toISOString() };
}

export function AnalyticsPage() {
  const { brand } = useOutletContext<Shell>();
  const [days, setDays] = useState(30);
  const range = useMemo(() => dayRange(days), [days]);
  const summaryQuery = useQuery({
    queryKey: ["analytics", brand?.id, range.from, range.to],
    queryFn: () => cf.analytics(brand!.id, range.from, range.to),
    enabled: Boolean(brand),
  });
  const pubsQuery = useQuery({
    queryKey: ["publications", brand?.id],
    queryFn: () => cf.publications(brand!.id),
    enabled: Boolean(brand),
  });

  if (!brand) {
    return (
      <main className="page">
        <EmptyState title="Нет бренда" hint="Сначала онбординг." cta="Онбординг" to="/onboarding" />
      </main>
    );
  }

  const channels = summaryQuery.data?.channels ?? [];

  return (
    <main className="page grid">
      <h1>Аналитика</h1>
      <ErrorBanner error={summaryQuery.error || pubsQuery.error} />
      <label className="field">
        Период, дней
        <input type="number" min={1} value={days} onChange={(e) => setDays(Number(e.target.value))} />
      </label>
      {channels.length === 0 ? (
        <EmptyState title="Нет снимков" hint="После публикаций метрики подтянутся джобой sync. Zeros не показываем, если канал unavailable." cta="Очередь" to="/queue" />
      ) : (
        <div className="cards">
          {channels.map((row) => (
            <div className="card" key={row.channel_type}>
              <h3>{label(CHANNEL_LABELS, row.channel_type)}</h3>
              <p>публикаций: {row.publications}</p>
              <p>failed: {row.failed}</p>
              {row.availability === "unavailable" ? (
                <p className="muted">метрики недоступны (не 0)</p>
              ) : (
                Object.entries(row.metrics).map(([key, value]) => (
                  <p key={key}>
                    {key}: {value.sum} ({value.availability})
                  </p>
                ))
              )}
            </div>
          ))}
        </div>
      )}
      <div className="panel">
        <h3>Публикации</h3>
        <table>
          <thead>
            <tr>
              <th>Когда</th>
              <th>Статус</th>
              <th>external_id</th>
            </tr>
          </thead>
          <tbody>
            {(pubsQuery.data ?? []).map((row) => (
              <tr key={row.id}>
                <td>{new Date(row.scheduled_at).toLocaleString("ru")}</td>
                <td>{row.status}</td>
                <td>{row.external_id ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
