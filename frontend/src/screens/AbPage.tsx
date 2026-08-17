import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import type { BrandPublic } from "../api/types";
import { EmptyState, ErrorBanner } from "../components/Status";

type Shell = { brand: BrandPublic | null };

function localInput(offsetMin: number): string {
  const date = new Date(Date.now() + offsetMin * 60 * 1000);
  date.setSeconds(0, 0);
  const iso = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString();
  return iso.slice(0, 16);
}

export function AbPage() {
  const { brand } = useOutletContext<Shell>();
  const queryClient = useQueryClient();
  const [pieceId, setPieceId] = useState("");
  const [variantA, setVariantA] = useState("");
  const [variantB, setVariantB] = useState("");
  const contentQuery = useQuery({
    queryKey: ["content", brand?.id],
    queryFn: () => cf.content(brand!.id),
    enabled: Boolean(brand),
  });
  const expQuery = useQuery({
    queryKey: ["experiments", brand?.id],
    queryFn: () => cf.experiments(brand!.id),
    enabled: Boolean(brand),
  });
  const create = useMutation({
    mutationFn: () =>
      cf.createExperiment(brand!.id, {
        piece_id: pieceId,
        variant_a_id: variantA,
        variant_b_id: variantB,
        channel_type: "telegram",
        mode: "sequential",
        primary_metric: "impressions",
        window_start: new Date().toISOString(),
        window_end: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
        schedule_a: new Date(localInput(2)).toISOString(),
        schedule_b: new Date(localInput(6)).toISOString(),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["experiments"] }),
  });
  const start = useMutation({
    mutationFn: (id: string) => cf.startExperiment(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["experiments"] }),
  });
  const stop = useMutation({
    mutationFn: (id: string) => cf.stopExperiment(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["experiments"] }),
  });
  const winner = useMutation({
    mutationFn: ({ id, variant_id }: { id: string; variant_id: string }) =>
      cf.winnerExperiment(id, variant_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["experiments"] }),
  });

  const piece = (contentQuery.data ?? []).find((row) => row.id === pieceId);

  if (!brand) {
    return (
      <main className="page">
        <EmptyState title="Нет бренда" hint="Сначала онбординг." cta="Онбординг" to="/onboarding" />
      </main>
    );
  }

  return (
    <main className="page grid">
      <h1>A/B эксперименты</h1>
      <p className="muted">Только sequential Telegram. Gmail split / WP title — 409.</p>
      <ErrorBanner error={expQuery.error || create.error || start.error || winner.error} />
      <form
        className="panel grid"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <label className="field">
          Материал
          <select
            value={pieceId}
            onChange={(e) => {
              setPieceId(e.target.value);
              const next = (contentQuery.data ?? []).find((row) => row.id === e.target.value);
              setVariantA(next?.variants[0]?.id ?? "");
              setVariantB(next?.variants[1]?.id ?? "");
            }}
          >
            <option value="">выберите</option>
            {(contentQuery.data ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                {row.type} · {row.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Variant A
          <select value={variantA} onChange={(e) => setVariantA(e.target.value)}>
            {(piece?.variants ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Variant B
          <select value={variantB} onChange={(e) => setVariantB(e.target.value)}>
            {(piece?.variants ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
        <button className="btn" type="submit" disabled={!pieceId || !variantA || !variantB}>
          Создать sequential TG
        </button>
      </form>
      {(expQuery.data ?? []).length === 0 ? (
        <EmptyState title="Нет экспериментов" hint="Нужны variant A и B одного поста." cta="Редактор" to="/content" />
      ) : (
        (expQuery.data ?? []).map((row) => (
          <div className="card" key={row.id}>
            <h3>
              {row.status} · {row.mode} · {row.channel_type}
            </h3>
            <p className="muted">
              окно {new Date(row.window_start).toLocaleString("ru")} — {new Date(row.window_end).toLocaleString("ru")}
            </p>
            {row.metrics ? <pre>{JSON.stringify(row.metrics, null, 2)}</pre> : null}
            <div className="row">
              <button className="btn" type="button" onClick={() => start.mutate(row.id)}>
                Start
              </button>
              <button className="btn secondary" type="button" onClick={() => stop.mutate(row.id)}>
                Stop early
              </button>
              <button className="btn" type="button" onClick={() => winner.mutate({ id: row.id, variant_id: row.variant_a_id })}>
                Winner A
              </button>
              <button className="btn" type="button" onClick={() => winner.mutate({ id: row.id, variant_id: row.variant_b_id })}>
                Winner B
              </button>
            </div>
          </div>
        ))
      )}
    </main>
  );
}
