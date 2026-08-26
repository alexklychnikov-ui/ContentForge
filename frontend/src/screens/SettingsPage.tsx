import { useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import type { BrandPublic } from "../api/types";
import { getSession, setBrandId } from "../auth/session";
import { EmptyState, ErrorBanner } from "../components/Status";

type Shell = { brand: BrandPublic | null; brands: BrandPublic[] };

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
  const save = useMutation({
    mutationFn: () =>
      cf.patchBrand(brand!.id, {
        timezone,
        default_locale: locale,
        auto_pipeline_enabled: autoPipeline,
        auto_pipeline_lead_hours: Number(leadHours),
        default_slot_hour: Number(slotHour),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["brands"] }),
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

  return (
    <main className="page grid">
      <h1>Настройки</h1>
      <ErrorBanner error={save.error || remove.error} />
      <div className="panel grid">
        <h3>Профиль</h3>
        <p>Email: {session?.user.email}</p>
        <p>Воркспейс: {session?.workspace.name}</p>
        <p>Роль: {session?.workspace.role}</p>
      </div>
      <div className="panel grid">
        <h3>Бренд</h3>
        <label className="field">
          Таймзона
          <input value={timezone} onChange={(e) => setTimezone(e.target.value)} />
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
