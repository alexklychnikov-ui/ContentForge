import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import type { BrandPublic, PiecePublic, QualityReview, VariantMeta, VariantPublic } from "../api/types";
import { useActionFeedback } from "../components/ActionFeedback";
import { AuthedMedia } from "../components/AuthedMedia";
import { EmptyState, ErrorBanner } from "../components/Status";
import {
  CHANNEL_LABELS,
  CONTENT_CREATE_TYPES,
  CONTENT_LABELS,
  FIELD_META,
  MVP_CHANNELS,
  PIECE_STATUS,
  TYPE_FIELD_BLURB,
  label,
} from "../labels";

type Shell = { brand: BrandPublic | null };

function readVariantMeta(payload: Record<string, unknown> | undefined): VariantMeta | null {
  const raw = payload?._meta;
  if (!raw || typeof raw !== "object") return null;
  return raw as VariantMeta;
}

function qualityLists(meta: VariantMeta | null): { blockers: string[]; warnings: string[] } {
  const quality = meta?.quality;
  if (!quality) return { blockers: [], warnings: [] };
  const blockers =
    (Array.isArray(quality.blockers) && quality.blockers.length > 0
      ? quality.blockers
      : quality.lint?.blockers) ?? [];
  const warnings =
    (Array.isArray(quality.warnings) && quality.warnings.length > 0
      ? quality.warnings
      : quality.lint?.warnings) ?? [];
  return {
    blockers: blockers.map(String),
    warnings: warnings.map(String),
  };
}

function groundingStatusLabel(status: string): string {
  if (status === "grounded") return "с опорой";
  if (status === "ungrounded") return "без опоры";
  if (status === "skipped") return "пропущено";
  if (status === "blocked") return "блокировано";
  return status;
}

function fieldsFor(type: PiecePublic["type"]): string[] {
  if (type === "social_post")
    return ["headline", "lead", "scene", "takeaway", "text", "cta", "hashtags", "alt_text"];
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

function pieceSnippet(item: PiecePublic): string {
  const payload = item.variants?.[0]?.payload ?? {};
  const candidates = [payload.text, payload.title, payload.subject];
  let raw = "";
  for (const value of candidates) {
    const text = Array.isArray(value) ? value.join(" ") : String(value ?? "").trim();
    if (text) {
      raw = text.replace(/\s+/g, " ");
      break;
    }
  }
  if (!raw) return "без текста";
  return raw.length > 50 ? `${raw.slice(0, 50)}…` : raw;
}

function fieldCaption(type: PiecePublic["type"], key: string): string {
  const meta = FIELD_META[type]?.[key];
  if (!meta) return key;
  if (meta.required) return `${meta.label} · обязательно`;
  return meta.label;
}

export function EditorPage() {
  const { brand } = useOutletContext<Shell>();
  const { pieceId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [type, setType] = useState<PiecePublic["type"]>("social_post");
  const [labelName, setLabelName] = useState("A");
  const [form, setForm] = useState<Record<string, string>>({});
  const channelParam = searchParams.get("channel");
  const dateParam = searchParams.get("date");
  const [channel, setChannel] = useState(() =>
    channelParam && (MVP_CHANNELS as readonly string[]).includes(channelParam)
      ? channelParam
      : "telegram",
  );
  const [scheduledAt, setScheduledAt] = useState(() =>
    dateParam && /^\d{4}-\d{2}-\d{2}$/.test(dateParam) ? `${dateParam}T12:00` : "",
  );
  const { trackAction, trackJob } = useActionFeedback();
  const [reviewResult, setReviewResult] = useState<QualityReview | null>(null);
  const [exportPreview, setExportPreview] = useState<string | null>(null);
  const textRef = useRef<HTMLTextAreaElement | null>(null);
  const coverInputRef = useRef<HTMLInputElement | null>(null);
  const autogenStarted = useRef(false);

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

  const visiblePieces = useMemo(
    () => (listQuery.data ?? []).filter((item) => item.status !== "archived"),
    [listQuery.data],
  );

  const piece = pieceQuery.data;
  const variants = piece?.variants ?? [];
  const current = useMemo(
    () => variants.find((item) => item.label === labelName) ?? variants[0] ?? null,
    [variants, labelName],
  );
  const variantMeta = useMemo(() => readVariantMeta(current?.payload), [current]);
  const qualityFromMeta = useMemo(() => qualityLists(variantMeta), [variantMeta]);
  const liveBlockers = reviewResult ? reviewResult.blockers : qualityFromMeta.blockers;
  const liveWarnings = reviewResult ? reviewResult.warnings : qualityFromMeta.warnings;
  const isApproved = Boolean(variantMeta?.approved_at) || piece?.status === "ready";

  useEffect(() => {
    setReviewResult(null);
    setExportPreview(null);
  }, [current?.id]);

  useEffect(() => {
    if (piece) {
      setType(piece.type);
      if (current) {
        setLabelName(current.label);
        setForm(payloadToForm(current.payload, piece.type));
      }
    }
  }, [piece, current]);

  useEffect(() => {
    if (channelParam && (MVP_CHANNELS as readonly string[]).includes(channelParam)) {
      setChannel(channelParam);
    }
  }, [channelParam]);

  useEffect(() => {
    if (!dateParam || !/^\d{4}-\d{2}-\d{2}$/.test(dateParam)) return;
    setScheduledAt((prev) => (prev ? prev : `${dateParam}T12:00`));
  }, [dateParam]);

  useEffect(() => {
    autogenStarted.current = false;
  }, [pieceId]);

  const createPiece = useMutation({
    mutationFn: () => trackAction("Новый черновик", () => cf.createPiece(brand!.id, { type })),
    onSuccess: (row) => {
      queryClient.invalidateQueries({ queryKey: ["content"] });
      navigate(`/content/${row.id}`);
    },
  });

  const archivePiece = useMutation({
    mutationFn: (id: string) =>
      trackAction("Удаление черновика", () => cf.patchPiece(id, { status: "archived" })),
    onSuccess: (_row, id) => {
      queryClient.invalidateQueries({ queryKey: ["content"] });
      if (pieceId === id) navigate("/content");
    },
  });

  function confirmArchive(id: string) {
    if (!window.confirm("Удалить черновик? Он исчезнет из списка.")) return;
    archivePiece.mutate(id);
  }

  const generate = useMutation({
    mutationFn: async () => {
      await trackJob(
        "Генерация текста",
        () => cf.generateContent(piece!.id, { variant_label: labelName, channel_type: channel }),
        { kind: "generate_content" },
      );
      await queryClient.invalidateQueries({ queryKey: ["piece", pieceId] });
    },
  });

  useEffect(() => {
    if (searchParams.get("autogen") !== "1") return;
    if (!piece || !pieceQuery.isSuccess) return;

    const stripAutogen = () => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete("autogen");
          return next;
        },
        { replace: true },
      );
    };

    if (variants.length > 0) {
      stripAutogen();
      return;
    }
    if (generate.isPending || autogenStarted.current) return;
    autogenStarted.current = true;
    stripAutogen();
    generate.mutate();
  }, [piece, pieceQuery.isSuccess, variants.length, searchParams, generate, setSearchParams]);

  const save = useMutation({
    mutationFn: () =>
      trackAction("Сохранение", () =>
        cf.patchVariant(piece!.id, current!.id, { payload: formToPayload(form, piece!.type) }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["piece", pieceId] }),
  });
  const addB = useMutation({
    mutationFn: () =>
      trackAction("Добавление варианта B", () =>
        cf.addVariant(piece!.id, { label: "B", payload: formToPayload(form, piece!.type) }),
      ),
    onSuccess: () => {
      setLabelName("B");
      queryClient.invalidateQueries({ queryKey: ["piece", pieceId] });
    },
  });
  const rewrite = useMutation({
    mutationFn: async () => {
      const el = textRef.current;
      const field = piece!.type === "social_post" ? "text" : "body_markdown";
      const start = el?.selectionStart ?? 0;
      const end = el?.selectionEnd ?? 0;
      await trackJob(
        "Переписывание фрагмента",
        () =>
          cf.rewrite(piece!.id, current!.id, {
            selection: { field, start, end },
            extra_instructions: "перепиши выделенное короче",
          }),
        { kind: "rewrite" },
      );
      await queryClient.invalidateQueries({ queryKey: ["piece", pieceId] });
    },
  });
  const schedule = useMutation({
    mutationFn: () =>
      trackAction("Постановка в очередь", () => {
        const account = (channelsQuery.data ?? []).find(
          (row) => row.type === channel && row.status === "connected",
        );
        return cf.schedule(brand!.id, {
          variant_id: current!.id,
          channel_account_id: account?.id,
          scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : undefined,
          stopword_override: false,
        });
      }),
  });
  const review = useMutation({
    mutationFn: () =>
      trackAction("Проверка качества", () => cf.reviewVariant(piece!.id, current!.id, { run_ai: true })),
    onSuccess: (row) => {
      setReviewResult(row);
      queryClient.invalidateQueries({ queryKey: ["piece", pieceId] });
    },
  });
  const approve = useMutation({
    mutationFn: () => trackAction("Утверждение варианта", () => cf.approveVariant(piece!.id, current!.id)),
    onSuccess: () => {
      setReviewResult(null);
      queryClient.invalidateQueries({ queryKey: ["piece", pieceId] });
      queryClient.invalidateQueries({ queryKey: ["content", brand?.id] });
    },
  });
  const generateCover = useMutation({
    mutationFn: async () => {
      await trackJob(
        "Генерация обложки",
        () => cf.generateCover(piece!.id, current!.id),
        { kind: "generate_cover", maxTicks: 180 },
      );
      await queryClient.invalidateQueries({ queryKey: ["piece", pieceId] });
    },
  });
  const approveCover = useMutation({
    mutationFn: () => trackAction("Одобрение обложки", () => cf.approveCover(piece!.id, current!.id)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["piece", pieceId] }),
  });
  const assignCover = useMutation({
    mutationFn: (file: File) =>
      trackAction("Загрузка обложки", () =>
        cf.uploadMedia(brand!.id, file).then((media) => cf.assignCover(piece!.id, current!.id, media.id)),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["piece", pieceId] }),
  });
  const manualExport = useMutation({
    mutationFn: () =>
      trackAction("Экспорт для ручной публикации", () => cf.exportVariant(current!.id, channel)),
    onSuccess: (row) => setExportPreview(JSON.stringify(row, null, 2)),
  });
  const coverMeta = useMemo(() => {
    const meta = current?.payload?._meta;
    if (!meta || typeof meta !== "object") return null;
    const cover = (meta as Record<string, unknown>).cover;
    if (!cover || typeof cover !== "object") return null;
    return cover as { approved_at?: string };
  }, [current?.payload]);
  const coverApproved = Boolean(coverMeta?.approved_at);
  const coverMediaId = current?.cover_media_id ?? null;
  const manualExportChannels = ["instagram", "tenchat", "vk"] as const;

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
      <ErrorBanner
        error={
          pieceQuery.error ||
          generate.error ||
          save.error ||
          schedule.error ||
          rewrite.error ||
          archivePiece.error ||
          review.error ||
          approve.error ||
          generateCover.error ||
          approveCover.error ||
          assignCover.error ||
          manualExport.error
        }
      />
      <div className="row">
        <label className="field">
          Тип
          <select value={type} onChange={(e) => setType(e.target.value as PiecePublic["type"])}>
            {CONTENT_CREATE_TYPES.map((key) => (
              <option key={key} value={key}>
                {label(CONTENT_LABELS, key)}
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
          {visiblePieces.length === 0 ? (
            <p className="muted">Пока нет единиц контента.</p>
          ) : (
            <ul>
              {visiblePieces.map((item) => (
                <li key={item.id} className="row">
                  <Link to={`/content/${item.id}`} className={item.id === pieceId ? "active" : undefined}>
                    {label(CONTENT_LABELS, item.type)} · {pieceSnippet(item)}
                    <span className="muted"> · {label(PIECE_STATUS, item.status)}</span>
                  </Link>
                  <button
                    className="btn secondary"
                    type="button"
                    disabled={archivePiece.isPending}
                    onClick={() => confirmArchive(item.id)}
                  >
                    Удалить
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="panel grid">
          {!pieceId ? (
            <EmptyState title="Выберите материал" hint="Или создайте черновик и нажмите «Сгенерировать»." cta="Календарь" to="/calendar" />
          ) : pieceQuery.isError ? (
            <p className="muted">Материал не загружен — см. ошибку выше.</p>
          ) : !piece ? (
            <p className="muted">Загрузка…</p>
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
                    Вариант {item.label} r{item.revision}
                  </button>
                ))}
                <button
                  className="btn secondary"
                  type="button"
                  onClick={() => addB.mutate()}
                  disabled={!current || variants.some((item) => item.label === "B")}
                >
                  Добавить вариант B
                </button>
                <button
                  className="btn secondary"
                  type="button"
                  disabled={archivePiece.isPending}
                  onClick={() => confirmArchive(piece.id)}
                >
                  Удалить
                </button>
              </div>
              <p className="muted">{TYPE_FIELD_BLURB[piece.type]}</p>
              {variantMeta ? (
                <div className="grid">
                  <div className="row" style={{ flexWrap: "wrap", gap: "0.35rem" }}>
                    {variantMeta.grounding_status ? (
                      <span className="chip">
                        Grounding: {groundingStatusLabel(variantMeta.grounding_status)}
                      </span>
                    ) : null}
                    {isApproved ? <span className="chip">подтверждён</span> : null}
                    {liveBlockers.length > 0 ? (
                      <span className="chip">блокеры: {liveBlockers.length}</span>
                    ) : null}
                  </div>
                  {variantMeta.warning ? (
                    <p className="muted">Grounding warning: {variantMeta.warning}</p>
                  ) : null}
                  {(variantMeta.references ?? []).length > 0 ? (
                    <p className="muted">
                      Источники:{" "}
                      {(variantMeta.references ?? [])
                        .map((ref) => ref.file_path || ref.id)
                        .filter(Boolean)
                        .slice(0, 6)
                        .join(" · ")}
                    </p>
                  ) : null}
                  {liveBlockers.length > 0 ? (
                    <ul>
                      {liveBlockers.map((item) => (
                        <li key={`b-${item}`} className="muted">
                          Блокер: {item}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {liveWarnings.length > 0 ? (
                    <ul>
                      {liveWarnings.map((item) => (
                        <li key={`w-${item}`} className="muted">
                          Warning: {item}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {reviewResult?.ai_review ? (
                    <p className="muted">
                      AI review: overall {reviewResult.ai_review.overall}/5
                      {reviewResult.ai_review.pass ? " · pass" : " · fail"}
                    </p>
                  ) : null}
                  <div className="row">
                    <button
                      className="btn secondary"
                      type="button"
                      disabled={!current || review.isPending}
                      onClick={() => review.mutate()}
                    >
                      Проверить качество
                    </button>
                    <button
                      className="btn"
                      type="button"
                      disabled={
                        !current ||
                        approve.isPending ||
                        liveBlockers.length > 0 ||
                        isApproved
                      }
                      onClick={() => approve.mutate()}
                    >
                      Подтвердить
                    </button>
                  </div>
                </div>
              ) : current ? (
                <div className="row">
                  <button
                    className="btn secondary"
                    type="button"
                    disabled={review.isPending}
                    onClick={() => review.mutate()}
                  >
                    Проверить качество
                  </button>
                  <button
                    className="btn"
                    type="button"
                    disabled={approve.isPending || liveBlockers.length > 0 || isApproved}
                    onClick={() => approve.mutate()}
                  >
                    Подтвердить
                  </button>
                </div>
              ) : null}
              {fieldsFor(piece.type).map((key) => {
                const meta = FIELD_META[piece.type]?.[key];
                return (
                  <label className="field" key={key}>
                    {fieldCaption(piece.type, key)}
                    {meta?.hint && !meta.required ? <span className="muted"> — {meta.hint}</span> : null}
                    <textarea
                      ref={key === "text" || key === "body_markdown" ? textRef : undefined}
                      value={form[key] ?? ""}
                      onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
                      disabled={current?.is_immutable}
                    />
                  </label>
                );
              })}
              <p className="muted">Лимит Telegram ~4096 символов. Хештеги — через пробел.</p>
              <div className="row">
                <button className="btn" type="button" disabled={!current || current.is_immutable} onClick={() => save.mutate()}>
                  Сохранить
                </button>
                <button className="btn secondary" type="button" onClick={() => generate.mutate()}>
                  Сгенерировать
                </button>
                <button className="btn secondary" type="button" disabled={!current} onClick={() => rewrite.mutate()}>
                  Переписать выделенное
                </button>
              </div>
              <p className="muted">Выдели фрагмент в основном тексте и нажми</p>
              <div className="card">
                <h3>Обложка</h3>
                {coverMediaId ? (
                  <p className="muted">
                    media: {coverMediaId.slice(0, 8)}…
                    {coverApproved ? " · одобрена" : " · не одобрена"}
                  </p>
                ) : (
                  <p className="muted">Обложка не назначена</p>
                )}
                {coverMediaId ? (
                  <AuthedMedia
                    mediaId={coverMediaId}
                    alt="cover preview"
                    style={{ maxWidth: 320, width: "100%", borderRadius: 8, display: "block" }}
                  />
                ) : null}
                <input
                  ref={coverInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  hidden
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    if (file) assignCover.mutate(file);
                  }}
                />
                <div className="row">
                  <button
                    className="btn secondary"
                    type="button"
                    disabled={!current || assignCover.isPending}
                    onClick={() => coverInputRef.current?.click()}
                  >
                    Загрузить
                  </button>
                  <button
                    className="btn secondary"
                    type="button"
                    disabled={!current || generateCover.isPending}
                    onClick={() => generateCover.mutate()}
                  >
                    {generateCover.isPending ? "Генерация…" : "Сгенерировать"}
                  </button>
                  <button
                    className="btn"
                    type="button"
                    disabled={!current || !coverMediaId || coverApproved || approveCover.isPending}
                    onClick={() => approveCover.mutate()}
                  >
                    Одобрить обложку
                  </button>
                </div>
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
              <p className="muted">Из календаря подставляется дата слота и 12:00. Пустое поле = отправить сразу.</p>
              <button className="btn" type="button" disabled={!current} onClick={() => schedule.mutate()}>
                Поставить в очередь
              </button>
              {schedule.data ? <p className="muted">Публикация {schedule.data.status}</p> : null}
              {(manualExportChannels as readonly string[]).includes(channel) ? (
                <div className="row">
                  <button
                    className="btn secondary"
                    type="button"
                    disabled={!current || manualExport.isPending}
                    onClick={() => manualExport.mutate()}
                  >
                    Экспорт для ручной публикации
                  </button>
                </div>
              ) : null}
              {exportPreview ? (
                <pre className="muted" style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
                  {exportPreview}
                </pre>
              ) : null}
            </>
          )}
        </div>
      </div>
    </main>
  );
}
