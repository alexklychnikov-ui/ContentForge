import { useEffect, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import type { BrandContentProfile, BrandPublic, GroundingResult, KnowledgeMode } from "../api/types";
import { getSession, setBrandId } from "../auth/session";
import { EmptyState, ErrorBanner } from "../components/Status";
import { timezoneSelectOptions } from "../labels";

type Shell = { brand: BrandPublic | null; brands: BrandPublic[] };

type ProfileForm = {
  positioning: string;
  audience_segments: string;
  audience_pains: string;
  content_pillars: string;
  proof_facts: string;
  preferred_cta_styles: string;
  banned_openers: string;
  structure_rules: string;
  knowledge_mode: KnowledgeMode;
  knowledge_filters: string;
  require_human_approval: boolean;
};

function lines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function profileToForm(profile: BrandContentProfile): ProfileForm {
  return {
    positioning: profile.positioning ?? "",
    audience_segments: (profile.audience_segments ?? []).join("\n"),
    audience_pains: (profile.audience_pains ?? []).join("\n"),
    content_pillars: (profile.content_pillars ?? []).join("\n"),
    proof_facts: (profile.proof_facts ?? []).join("\n"),
    preferred_cta_styles: (profile.preferred_cta_styles ?? []).join("\n"),
    banned_openers: (profile.banned_openers ?? []).join("\n"),
    structure_rules: profile.structure_rules ?? "",
    knowledge_mode: profile.knowledge_mode ?? "off",
    knowledge_filters: (profile.knowledge_filters ?? []).join("\n"),
    require_human_approval: profile.require_human_approval ?? true,
  };
}

const EMPTY_PROFILE: ProfileForm = {
  positioning: "",
  audience_segments: "",
  audience_pains: "",
  content_pillars: "",
  proof_facts: "",
  preferred_cta_styles: "",
  banned_openers: "",
  structure_rules: "",
  knowledge_mode: "off",
  knowledge_filters: "",
  require_human_approval: true,
};

function truncate(text: string, max = 280): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max)}…`;
}

function groundingStatusLabel(status: string): string {
  if (status === "grounded") return "с опорой";
  if (status === "ungrounded") return "без опоры";
  if (status === "skipped") return "пропущено";
  if (status === "blocked") return "блокировано";
  return status;
}

export function SettingsPage() {
  const { brand, brands } = useOutletContext<Shell>();
  const session = getSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [timezone, setTimezone] = useState(brand?.timezone ?? "Europe/Moscow");
  const [locale, setLocale] = useState(brand?.default_locale ?? "ru");
  const [autoPipeline, setAutoPipeline] = useState(brand?.auto_pipeline_enabled ?? false);
  const [leadHours, setLeadHours] = useState(String(brand?.auto_pipeline_lead_hours ?? 24));
  const [slotHour, setSlotHour] = useState(String(brand?.default_slot_hour ?? 12));
  const [profileForm, setProfileForm] = useState<ProfileForm>(EMPTY_PROFILE);
  const [preview, setPreview] = useState<GroundingResult | null>(null);

  const profileQuery = useQuery({
    queryKey: ["content-profile", brand?.id],
    queryFn: () => cf.getContentProfile(brand!.id),
    enabled: Boolean(brand),
  });

  useEffect(() => {
    if (!brand) return;
    setTimezone(brand.timezone ?? "Europe/Moscow");
    setLocale(brand.default_locale ?? "ru");
    setAutoPipeline(brand.auto_pipeline_enabled ?? false);
    setLeadHours(String(brand.auto_pipeline_lead_hours ?? 24));
    setSlotHour(String(brand.default_slot_hour ?? 12));
    setProfileForm(EMPTY_PROFILE);
    setPreview(null);
  }, [brand?.id]);

  useEffect(() => {
    if (profileQuery.data && profileQuery.data.brand_id === brand?.id) {
      setProfileForm(profileToForm(profileQuery.data));
    }
  }, [profileQuery.data, brand?.id]);

  const save = useMutation({
    mutationFn: () =>
      cf.patchBrand(brand!.id, {
        timezone,
        default_locale: locale,
        auto_pipeline_enabled: autoPipeline,
        auto_pipeline_lead_hours: Number(leadHours),
        default_slot_hour: Number(slotHour),
      }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["brands"] });
      setTimezone(updated.timezone ?? "Europe/Moscow");
      setLocale(updated.default_locale ?? "ru");
      setAutoPipeline(updated.auto_pipeline_enabled ?? false);
      setLeadHours(String(updated.auto_pipeline_lead_hours ?? 24));
      setSlotHour(String(updated.default_slot_hour ?? 12));
    },
  });

  const saveProfile = useMutation({
    mutationFn: () =>
      cf.patchContentProfile(brand!.id, {
        positioning: profileForm.positioning,
        audience_segments: lines(profileForm.audience_segments),
        audience_pains: lines(profileForm.audience_pains),
        content_pillars: lines(profileForm.content_pillars),
        proof_facts: lines(profileForm.proof_facts),
        preferred_cta_styles: lines(profileForm.preferred_cta_styles),
        banned_openers: lines(profileForm.banned_openers),
        structure_rules: profileForm.structure_rules,
        knowledge_mode: profileForm.knowledge_mode,
        knowledge_filters: lines(profileForm.knowledge_filters),
        require_human_approval: profileForm.require_human_approval,
      }),
    onSuccess: (row) => {
      setProfileForm(profileToForm(row));
      queryClient.setQueryData(["content-profile", brand!.id], row);
    },
  });

  const applyPreset = useMutation({
    mutationFn: () => cf.applyContentProfilePreset(brand!.id, "alexander_personal"),
    onSuccess: (row) => {
      setProfileForm(profileToForm(row));
      queryClient.setQueryData(["content-profile", brand!.id], row);
    },
  });

  const previewKnowledge = useMutation({
    mutationFn: () => {
      const query =
        brand?.niche?.trim() ||
        lines(profileForm.knowledge_filters)[0] ||
        "правила постов TenChat";
      return cf.previewKnowledge(brand!.id, { query, mode: "mix" });
    },
    onSuccess: (row) => setPreview(row),
    onError: () => setPreview(null),
  });

  const remove = useMutation({
    mutationFn: () => cf.deleteBrand(brand!.id),
    onSuccess: () => {
      const next = brands.find((item) => item.id !== brand?.id);
      setBrandId(next?.id ?? null);
      queryClient.invalidateQueries({ queryKey: ["brands"] });
      navigate(next ? "/" : "/onboarding");
    },
  });

  if (!brand) {
    return (
      <main className="page">
        <EmptyState title="Нет бренда" hint="Создайте Brand Kit." cta="Онбординг" to="/onboarding" />
      </main>
    );
  }

  function setListField<K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) {
    setProfileForm((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <main className="page grid">
      <h1>Настройки</h1>
      <ErrorBanner
        error={
          save.error ||
          remove.error ||
          profileQuery.error ||
          saveProfile.error ||
          applyPreset.error ||
          previewKnowledge.error
        }
      />
      <div className="panel grid">
        <h3>Профиль</h3>
        <p>Email: {session?.user.email}</p>
        <p>
          Воркспейс: {session?.workspace.name}{" "}
          <span className="muted">(аккаунт, не бренд)</span>
        </p>
        <p>
          Активный бренд: <strong>{brand.name}</strong>
        </p>
        <p>Роль: {session?.workspace.role}</p>
      </div>
      <div className="panel grid">
        <h3>Бренды</h3>
        <p className="muted">
          Активный: <strong>{brand.name}</strong>. Переключается в шапке.
          {brands.length > 1 ? ` Всего брендов: ${brands.length}.` : ""}
        </p>
        <ul className="muted">
          {brands.map((item) => (
            <li key={item.id}>
              {item.name}
              {item.id === brand.id ? " ← сейчас" : ""}
              {` · ${item.timezone}`}
            </li>
          ))}
        </ul>
        <button className="btn" type="button" onClick={() => navigate("/onboarding?new=1")}>
          Новый бренд
        </button>
      </div>
      <div className="panel grid">
        <h3>Настройки бренда: {brand.name}</h3>
        <label className="field">
          Таймзона
          <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
            {timezoneSelectOptions(timezone).map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Язык контента (UI остаётся русским)
          <select value={locale} onChange={(e) => setLocale(e.target.value as "ru" | "en")}>
            <option value="ru">ru</option>
            <option value="en">en</option>
          </select>
        </label>
        <label className="field">
          <span className="row" style={{ gap: "0.5rem", alignItems: "center" }}>
            <input
              type="checkbox"
              checked={autoPipeline}
              onChange={(e) => setAutoPipeline(e.target.checked)}
            />
            Автоподготовка слотов
          </span>
        </label>
        <label className="field">
          За сколько часов готовить (lead hours)
          <input
            type="number"
            min={1}
            max={168}
            value={leadHours}
            onChange={(e) => setLeadHours(e.target.value)}
            disabled={!autoPipeline}
          />
        </label>
        <label className="field">
          Час слота (0–23, в таймзоне бренда)
          <input
            type="number"
            min={0}
            max={23}
            value={slotHour}
            onChange={(e) => setSlotHour(e.target.value)}
          />
        </label>
        <p className="muted">
          Если включено: за lead hours до даты слота (утверждённый план) система сама сгенерит текст и поставит в
          очередь на этот час. Канал должен быть подключён.
        </p>
        <button className="btn" type="button" onClick={() => save.mutate()}>
          Сохранить
        </button>
      </div>
      <div className="panel grid">
        <h3>Контент-профиль: {brand.name}</h3>
        {profileQuery.isLoading ? <p className="muted">Загрузка профиля…</p> : null}
        <label className="field">
          Позиционирование
          <textarea
            value={profileForm.positioning}
            onChange={(e) => setListField("positioning", e.target.value)}
            rows={3}
          />
        </label>
        <label className="field">
          Сегменты аудитории (по одному на строку)
          <textarea
            value={profileForm.audience_segments}
            onChange={(e) => setListField("audience_segments", e.target.value)}
            rows={3}
          />
        </label>
        <label className="field">
          Боли аудитории (по одному на строку)
          <textarea
            value={profileForm.audience_pains}
            onChange={(e) => setListField("audience_pains", e.target.value)}
            rows={3}
          />
        </label>
        <label className="field">
          Контент-столпы (по одному на строку)
          <textarea
            value={profileForm.content_pillars}
            onChange={(e) => setListField("content_pillars", e.target.value)}
            rows={3}
          />
        </label>
        <label className="field">
          Факты / доказательства (по одному на строку)
          <textarea
            value={profileForm.proof_facts}
            onChange={(e) => setListField("proof_facts", e.target.value)}
            rows={3}
          />
        </label>
        <label className="field">
          Предпочтительные CTA (по одному на строку)
          <textarea
            value={profileForm.preferred_cta_styles}
            onChange={(e) => setListField("preferred_cta_styles", e.target.value)}
            rows={2}
          />
        </label>
        <label className="field">
          Запрещённые открывашки (по одному на строку)
          <textarea
            value={profileForm.banned_openers}
            onChange={(e) => setListField("banned_openers", e.target.value)}
            rows={2}
          />
        </label>
        <label className="field">
          Правила структуры
          <textarea
            value={profileForm.structure_rules}
            onChange={(e) => setListField("structure_rules", e.target.value)}
            rows={4}
          />
        </label>
        <label className="field">
          Режим знаний (LightRAG)
          <select
            value={profileForm.knowledge_mode}
            onChange={(e) => setListField("knowledge_mode", e.target.value as KnowledgeMode)}
          >
            <option value="off">off — выкл</option>
            <option value="optional">optional — по возможности</option>
            <option value="required">required — обязательно</option>
          </select>
        </label>
        <label className="field">
          Фильтры знаний (по одному на строку)
          <textarea
            value={profileForm.knowledge_filters}
            onChange={(e) => setListField("knowledge_filters", e.target.value)}
            rows={2}
          />
        </label>
        <label className="field">
          <span className="row" style={{ gap: "0.5rem", alignItems: "center" }}>
            <input
              type="checkbox"
              checked={profileForm.require_human_approval}
              onChange={(e) => setListField("require_human_approval", e.target.checked)}
            />
            Требовать подтверждение человеком перед автопостингом
          </span>
        </label>
        <div className="row">
          <button
            className="btn"
            type="button"
            disabled={saveProfile.isPending}
            onClick={() => saveProfile.mutate()}
          >
            Сохранить
          </button>
          <button
            className="btn secondary"
            type="button"
            disabled={applyPreset.isPending}
            onClick={() => applyPreset.mutate()}
          >
            Применить пресет «Личный бренд Александра»
          </button>
          <button
            className="btn secondary"
            type="button"
            disabled={previewKnowledge.isPending}
            onClick={() => previewKnowledge.mutate()}
          >
            Проверить LightRAG
          </button>
        </div>
        {saveProfile.isSuccess ? <p className="muted">Контент-профиль сохранён.</p> : null}
        {applyPreset.isSuccess ? <p className="muted">Пресет применён.</p> : null}
        {preview ? (
          <div className="grid">
            <p>
              LightRAG: <span className="chip">{groundingStatusLabel(preview.status)}</span>
              {preview.error_code ? <span className="chip">{preview.error_code}</span> : null}
            </p>
            {preview.warning ? <p className="muted">Warning: {truncate(preview.warning, 200)}</p> : null}
            {preview.error_message ? (
              <p className="muted">Ошибка: {truncate(preview.error_message, 200)}</p>
            ) : null}
            {preview.context ? <p className="muted">Контекст: {truncate(preview.context)}</p> : null}
            {(preview.references ?? []).length > 0 ? (
              <ul>
                {preview.references.slice(0, 8).map((ref) => (
                  <li key={ref.id} className="muted">
                    {ref.file_path || ref.id}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">Референсов нет.</p>
            )}
          </div>
        ) : null}
      </div>
      <div className="panel">
        <h3>Команда</h3>
        <p className="muted">Инвайт Viewer — фаза 2, не реализован.</p>
      </div>
      <div className="panel">
        <h3>Опасная зона</h3>
        <button
          className="btn danger"
          type="button"
          onClick={() => {
            if (window.confirm("Удалить бренд?")) remove.mutate();
          }}
        >
          Удалить бренд
        </button>
      </div>
    </main>
  );
}
