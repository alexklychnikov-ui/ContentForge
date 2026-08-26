import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import type { BrandPublic, PiecePublic } from "../api/types";
import { EmptyState, ErrorBanner } from "../components/Status";
import { CHANNEL_LABELS, CONTENT_LABELS, label } from "../labels";

type Shell = { brand: BrandPublic | null };

const EXP_STATUS: Record<string, string> = {
  draft: "черновик",
  running: "идёт",
  completed: "завершён",
  cancelled: "отменён",
  tie: "ничья",
};

const EXP_MODE: Record<string, string> = {
  sequential: "по очереди",
  split: "сплит",
};

function localInput(offsetMin: number): string {
  const date = new Date(Date.now() + offsetMin * 60_000);
  date.setSeconds(0, 0);
  const iso = new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString();
  return iso.slice(0, 16);
}

function pieceOptionLabel(row: PiecePublic): string {
  const payload = row.variants?.[0]?.payload ?? {};
  const candidates = [payload.subject, payload.title, payload.text];
  let snippet = "";
  for (const value of candidates) {
    const text = Array.isArray(value) ? value.join(" ") : String(value ?? "").trim();
    if (text) {
      snippet = text.replace(/\s+/g, " ");
      break;
    }
  }
  if (snippet.length > 40) snippet = `${snippet.slice(0, 40)}…`;
  const typeName = label(CONTENT_LABELS, row.type);
  return snippet ? `${typeName} · ${snippet}` : `${typeName} · ${row.id.slice(0, 8)}`;
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

  const pieces = useMemo(
    () => (contentQuery.data ?? []).filter((row) => row.status !== "archived"),
    [contentQuery.data],
  );

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

  const piece = pieces.find((row) => row.id === pieceId);

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
      <p className="muted">
        MVP: только Telegram, режим «по очереди». Сначала публикуется вариант A, через несколько минут — B.
        Сплит Gmail / WordPress пока недоступны.
      </p>
      <p className="muted">
        Как пользоваться: в Редакторе сделай два варианта текста (A и B) у одного поста → выбери материал здесь →
        «Создать тест» → «Запустить» → по метрикам или вручную отметь победителя.
      </p>
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
              const next = pieces.find((row) => row.id === e.target.value);
              setVariantA(next?.variants[0]?.id ?? "");
              setVariantB(next?.variants[1]?.id ?? "");
            }}
          >
            <option value="">выберите</option>
            {pieces.map((row) => (
              <option key={row.id} value={row.id}>
                {pieceOptionLabel(row)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Вариант A
          <select value={variantA} onChange={(e) => setVariantA(e.target.value)}>
            {(piece?.variants ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                Вариант {row.label} (правка {row.revision})
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Вариант B
          <select value={variantB} onChange={(e) => setVariantB(e.target.value)}>
            {(piece?.variants ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                Вариант {row.label} (правка {row.revision})
              </option>
            ))}
          </select>
        </label>
        <button className="btn" type="submit" disabled={!pieceId || !variantA || !variantB || variantA === variantB}>
          Создать тест (Telegram по очереди)
        </button>
      </form>
      {(expQuery.data ?? []).length === 0 ? (
        <EmptyState
          title="Нет экспериментов"
          hint="Нужны два разных варианта (A и B) у одного поста в Редакторе."
          cta="Редактор"
          to="/content"
        />
      ) : (
        (expQuery.data ?? []).map((row) => (
          <div className="card" key={row.id}>
            <h3>
              {label(EXP_STATUS, row.status)} · {label(EXP_MODE, row.mode)} ·{" "}
              {label(CHANNEL_LABELS, row.channel_type)}
            </h3>
            <p className="muted">
              Окно наблюдения: {new Date(row.window_start).toLocaleString("ru")} —{" "}
              {new Date(row.window_end).toLocaleString("ru")}
            </p>
            {row.winner_variant_id ? (
              <p className="muted">
                Победитель:{" "}
                {row.winner_variant_id === row.variant_a_id
                  ? "вариант A"
                  : row.winner_variant_id === row.variant_b_id
                    ? "вариант B"
                    : row.winner_variant_id.slice(0, 8)}
              </p>
            ) : null}
            {row.metrics ? <pre>{JSON.stringify(row.metrics, null, 2)}</pre> : null}
            <div className="row">
              <button className="btn" type="button" onClick={() => start.mutate(row.id)}>
                Запустить
              </button>
              <button className="btn secondary" type="button" onClick={() => stop.mutate(row.id)}>
                Остановить досрочно
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => winner.mutate({ id: row.id, variant_id: row.variant_a_id })}
              >
                Победитель A
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => winner.mutate({ id: row.id, variant_id: row.variant_b_id })}
              >
                Победитель B
              </button>
            </div>
          </div>
        ))
      )}
    </main>
  );
}
