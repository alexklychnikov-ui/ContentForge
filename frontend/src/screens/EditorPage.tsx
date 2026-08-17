import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import { pollJob } from "../api/client";
import type { BrandPublic, PiecePublic, VariantPublic } from "../api/types";
import { pushRecentJob } from "../auth/session";
import { EmptyState, ErrorBanner, JobBanner } from "../components/Status";
import { CHANNEL_LABELS, CONTENT_LABELS, MVP_CHANNELS, label } from "../labels";

type Shell = { brand: BrandPublic | null };

function fieldsFor(type: PiecePublic["type"]): string[] {
  if (type === "social_post") return ["text", "cta", "hashtags", "alt_text"];
  if (type === "article") return ["title", "slug", "excerpt", "body_markdown", "seo_title", "seo_description"];
  return ["subject", "preheader", "body_markdown"];
}

function payloadToForm(payload: Record<string, unknown>, type: PiecePublic["type"]): Record<string, string> {
  const next: Record<string, string> = {};
  for (const key of fieldsFor(type)) {
    const value = payload[key];
    next[key] = Array.isArray(value) ? value.join(" ") : String(value ?? "");
  }
  return next;
}

function formToPayload(form: Record<string, string>, type: PiecePublic["type"]): Record<string, unknown> {
  const payload: Record<string, unknown> = { ...form };
  if (type === "social_post") {
    payload.hashtags = form.hashtags.split(/\s+/).filter(Boolean);
  }
  return payload;
}

export function EditorPage() {
  const { brand } = useOutletContext<Shell>();
  const { pieceId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [type, setType] = useState<PiecePublic["type"]>("social_post");
  const [labelName, setLabelName] = useState("A");
  const [form, setForm] = useState<Record<string, string>>({});
  const [channel, setChannel] = useState("telegram");
  const [scheduledAt, setScheduledAt] = useState("");
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const textRef = useRef<HTMLTextAreaElement | null>(null);

  const listQuery = useQuery({
    queryKey: ["content", brand?.id],
    queryFn: () => cf.content(brand!.id),
    enabled: Boolean(brand),
  });
  const pieceQuery = useQuery({
    queryKey: ["piece", pieceId],
    queryFn: () => cf.getPiece(pieceId!),
    enabled: Boolean(pieceId),
  });
  const channelsQuery = useQuery({
    queryKey: ["channels", brand?.id],
    queryFn: () => cf.channels(brand!.id),
    enabled: Boolean(brand),
  });

  const piece = pieceQuery.data;
  const variants = piece?.variants ?? [];
  const current = useMemo(
    () => variants.find((item) => item.label === labelName) ?? variants[0] ?? null,
    [variants, labelName],
  );

  useEffect(() => {
    if (piece) {
      setType(piece.type);
      if (current) {
        setLabelName(current.label);
        setForm(payloadToForm(current.payload, piece.type));
      }
    }
  }, [piece, current]);

  const createPiece = useMutation({
    mutationFn: () => cf.createPiece(brand!.id, { type }),
    onSuccess: (row) => {
      queryClient.invalidateQueries({ queryKey: ["content"] });
      navigate(`/content/${row.id}`);
    },
  });

  async function runJob(start: () => Promise<{ job_id: string }>, kind: string) {
    setJobError(null);
    const accepted = await start();
    pushRecentJob({ id: accepted.job_id, type: kind, at: new Date().toISOString() });
    const done = await pollJob(accepted.job_id, (id) => cf.job(id), { intervalMs: 700, maxTicks: 60 });
    setJobStatus(done.status);
    setJobError(done.error);
    await queryClient.invalidateQueries({ queryKey: ["piece", pieceId] });
  }

  const generate = useMutation({
    mutationFn: () =>
      runJob(() => cf.generateContent(piece!.id, { variant_label: labelName, channel_type: channel }), "generate_content"),
  });
  const save = useMutation({
    mutationFn: () =>
      cf.patchVariant(piece!.id, current!.id, { payload: formToPayload(form, piece!.type) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["piece", pieceId] }),
  });
  const addB = useMutation({
    mutationFn: () => cf.addVariant(piece!.id, { label: "B", payload: formToPayload(form, piece!.type) }),
    onSuccess: () => {
      setLabelName("B");
      queryClient.invalidateQueries({ queryKey: ["piece", pieceId] });
    },
  });
  const rewrite = useMutation({
    mutationFn: () => {
      const el = textRef.current;
      const field = piece!.type === "social_post" ? "text" : "body_markdown";
      const start = el?.selectionStart ?? 0;
      const end = el?.selectionEnd ?? 0;
      return runJob(
        () =>
          cf.rewrite(piece!.id, current!.id, {
            selection: { field, start, end },
            extra_instructions: "перепиши выделенное короче",
          }),
        "rewrite",
      );
    },
  });
  const schedule = useMutation({
    mutationFn: () => {
      const account = (channelsQuery.data ?? []).find((row) => row.type === channel && row.status === "connected");
      return cf.schedule(brand!.id, {
        variant_id: current!.id,
        channel_account_id: account?.id,
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : undefined,
        stopword_override: false,
      });
    },
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
      <h1>Редактор контента</h1>
      <ErrorBanner error={pieceQuery.error || generate.error || save.error || schedule.error || rewrite.error} />
      <JobBanner status={jobStatus} error={jobError} label="AI-задача" />
      <div className="row">
        <label className="field">
          Тип
          <select value={type} onChange={(e) => setType(e.target.value as PiecePublic["type"])}>
            {Object.entries(CONTENT_LABELS).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <button className="btn" type="button" onClick={() => createPiece.mutate()}>
          Новый черновик
        </button>
      </div>
      <div className="split">
        <div className="panel">
          <h3>Список</h3>
          {(listQuery.data ?? []).length === 0 ? (
            <p className="muted">Пока нет единиц контента.</p>
          ) : (
            <ul>
              {(listQuery.data ?? []).map((item) => (
                <li key={item.id}>
                  <Link to={`/content/${item.id}`}>
                    {label(CONTENT_LABELS, item.type)} · {item.status}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="panel grid">
          {!piece ? (
            <EmptyState title="Выберите материал" hint="Или создайте черновик и сгенерируйте variant A." cta="Календарь" to="/calendar" />
          ) : (
            <>
              <div className="row">
                {variants.map((item: VariantPublic) => (
                  <button
                    key={item.id}
                    className={`btn ${item.label === current?.label ? "" : "secondary"}`}
                    type="button"
                    onClick={() => setLabelName(item.label)}
                  >
                    {item.label} r{item.revision}
                  </button>
                ))}
                <button className="btn secondary" type="button" onClick={() => addB.mutate()} disabled={!current}>
                  Variant B
                </button>
              </div>
              {fieldsFor(piece.type).map((key) => (
                <label className="field" key={key}>
                  {key}
                  <textarea
                    ref={key === "text" || key === "body_markdown" ? textRef : undefined}
                    value={form[key] ?? ""}
                    onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
                    disabled={current?.is_immutable}
                  />
                </label>
              ))}
              <p className="muted">Лимит Telegram ~4096 символов. Хештеги — через пробел.</p>
              <div className="row">
                <button className="btn" type="button" disabled={!current || current.is_immutable} onClick={() => save.mutate()}>
                  Сохранить
                </button>
                <button className="btn secondary" type="button" onClick={() => generate.mutate()}>
                  Сгенерировать
                </button>
                <button className="btn secondary" type="button" disabled={!current} onClick={() => rewrite.mutate()}>
                  Rewrite selection
                </button>
              </div>
              <label className="field">
                Канал
                <select value={channel} onChange={(e) => setChannel(e.target.value)}>
                  {MVP_CHANNELS.map((item) => (
                    <option key={item} value={item}>
                      {label(CHANNEL_LABELS, item)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Расписание
                <input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} />
              </label>
              <button className="btn" type="button" disabled={!current} onClick={() => schedule.mutate()}>
                Поставить в очередь
              </button>
              {schedule.data ? <p className="muted">Публикация {schedule.data.status}</p> : null}
            </>
          )}
        </div>
      </div>
    </main>
  );
}
