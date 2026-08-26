import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import type { BrandPublic } from "../api/types";
import { EmptyState, ErrorBanner } from "../components/Status";
import { CHANNEL_LABELS, PUB_STATUS, label } from "../labels";

type Shell = { brand: BrandPublic | null };

export function QueuePage() {
  const { brand } = useOutletContext<Shell>();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const pubsQuery = useQuery({
    queryKey: ["publications", brand?.id, status],
    queryFn: () => cf.publications(brand!.id, status || undefined),
    enabled: Boolean(brand),
    refetchInterval: 4000,
  });
  const cancel = useMutation({
    mutationFn: (id: string) => cf.cancelPublication(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["publications"] }),
  });
  const retry = useMutation({
    mutationFn: (id: string) => cf.retryPublication(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["publications"] }),
  });
  const manual = useMutation({
    mutationFn: (id: string) => cf.markManual(id, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["publications"] }),
  });

  if (!brand) {
    return (
      <main className="page">
        <EmptyState title="Нет бренда" hint="Сначала онбординг." cta="Онбординг" to="/onboarding" />
      </main>
    );
  }

  const rows = pubsQuery.data ?? [];

  return (
    <main className="page grid">
      <h1>Очередь публикаций</h1>
      <ErrorBanner error={pubsQuery.error || cancel.error || retry.error} />
      <label className="field">
        Статус
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">все</option>
          {Object.keys(PUB_STATUS).map((key) => (
            <option key={key} value={key}>
              {PUB_STATUS[key]}
            </option>
          ))}
        </select>
      </label>
      {rows.length === 0 ? (
        <EmptyState title="Очередь пуста" hint="Поставьте слот в расписание из редактора." cta="Редактор" to="/content" />
      ) : (
        <table>
          <thead>
            <tr>
              <th>Время</th>
              <th>Канал</th>
              <th>Статус</th>
              <th>Ошибка</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{new Date(row.scheduled_at).toLocaleString("ru")}</td>
                <td>{label(CHANNEL_LABELS, row.channel_type)}</td>
                <td>{label(PUB_STATUS, row.status)}</td>
                <td>{row.error_message ?? row.error_code ?? ""}</td>
                <td className="row">
                  {row.piece_id ? (
                    <Link to={`/content/${row.piece_id}?channel=${encodeURIComponent(row.channel_type)}`}>
                      Контент
                    </Link>
                  ) : (
                    <Link to="/content">Контент</Link>
                  )}
                  {row.status === "scheduled" ? (
                    <button className="btn secondary" type="button" onClick={() => cancel.mutate(row.id)}>
                      Cancel
                    </button>
                  ) : null}
                  {row.status === "failed" || row.status === "dead" ? (
                    <button className="btn" type="button" onClick={() => retry.mutate(row.id)}>
                      Retry
                    </button>
                  ) : null}
                  <button className="btn secondary" type="button" onClick={() => manual.mutate(row.id)}>
                    Copy/manual
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
