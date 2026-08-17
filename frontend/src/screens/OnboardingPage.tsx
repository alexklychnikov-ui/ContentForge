import { useEffect, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { cf } from "../api/cf";
import type { BrandPublic } from "../api/types";
import { setBrandId } from "../auth/session";
import { ErrorBanner } from "../components/Status";
import { useQueryClient } from "@tanstack/react-query";

const schema = z.object({
  name: z.string().min(1, "Название"),
  niche: z.string().min(1, "Ниша"),
  timezone: z.string().min(1),
  default_locale: z.enum(["ru", "en"]),
  audience: z.string().min(1, "ЦА"),
  voice_tone: z.string().min(1, "Голос"),
  stopwords: z.string(),
  offers: z.string().min(1, "Нужен хотя бы один оффер"),
  example_posts: z.string(),
});

type Values = z.infer<typeof schema>;
type Shell = { brand: BrandPublic | null; brands: BrandPublic[] };

const STEPS = ["О бренде", "ЦА и голос", "Офферы", "Эталоны", "Каналы"];

function lines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { brand } = useOutletContext<Shell>();
  const [step, setStep] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [skipWarn, setSkipWarn] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: brand?.name ?? "",
      niche: brand?.niche ?? "",
      timezone: brand?.timezone ?? "Europe/Moscow",
      default_locale: brand?.default_locale ?? "ru",
      audience: brand?.audience ?? "",
      voice_tone: brand?.voice_tone ?? "",
      stopwords: (brand?.stopwords ?? []).join("\n"),
      offers: (brand?.offers ?? []).join("\n"),
      example_posts: (brand?.example_posts ?? []).join("\n"),
    },
  });

  useEffect(() => {
    if (brand) {
      form.reset({
        name: brand.name,
        niche: brand.niche,
        timezone: brand.timezone,
        default_locale: brand.default_locale,
        audience: brand.audience,
        voice_tone: brand.voice_tone,
        stopwords: brand.stopwords.join("\n"),
        offers: brand.offers.join("\n"),
        example_posts: brand.example_posts.join("\n"),
      });
    }
  }, [brand, form]);

  async function save(values: Values, goChannels: boolean) {
    setError(null);
    const body = {
      name: values.name,
      niche: values.niche,
      timezone: values.timezone,
      default_locale: values.default_locale,
      audience: values.audience,
      voice_tone: values.voice_tone,
      stopwords: lines(values.stopwords),
      offers: lines(values.offers),
      example_posts: lines(values.example_posts),
    };
    try {
      const saved = brand ? await cf.patchBrand(brand.id, body) : await cf.createBrand(body);
      setBrandId(saved.id);
      await queryClient.invalidateQueries({ queryKey: ["brands"] });
      if (goChannels) {
        navigate("/channels");
      } else {
        navigate("/");
      }
    } catch (err) {
      setError(err);
    }
  }

  return (
    <main className="page">
      <h1>Онбординг Brand Kit</h1>
      <div className="steps">
        {STEPS.map((name, index) => (
          <span key={name} className={index === step ? "on" : ""}>
            {index + 1}. {name}
          </span>
        ))}
      </div>
      <ErrorBanner error={error} />
      <form className="panel grid" onSubmit={(event) => event.preventDefault()}>
        {step === 0 ? (
          <>
            <label className="field">
              Название
              <input {...form.register("name")} />
            </label>
            <label className="field">
              Ниша
              <textarea {...form.register("niche")} />
            </label>
            <label className="field">
              Таймзона
              <input {...form.register("timezone")} />
            </label>
            <label className="field">
              Язык контента
              <select {...form.register("default_locale")}>
                <option value="ru">ru</option>
                <option value="en">en</option>
              </select>
            </label>
          </>
        ) : null}
        {step === 1 ? (
          <>
            <label className="field">
              ЦА
              <textarea {...form.register("audience")} />
            </label>
            <label className="field">
              Голос
              <textarea {...form.register("voice_tone")} />
            </label>
            <label className="field">
              Стоп-слова (по строке)
              <textarea {...form.register("stopwords")} />
            </label>
          </>
        ) : null}
        {step === 2 ? (
          <label className="field">
            Офферы (по строке, минимум один)
            <textarea {...form.register("offers")} />
          </label>
        ) : null}
        {step === 3 ? (
          <label className="field">
            Эталонные посты (по строке)
            <textarea {...form.register("example_posts")} />
          </label>
        ) : null}
        {step === 4 ? (
          <div className="empty">
            <p>Каналы можно подключить сейчас или пропустить — без каналов автопостинг недоступен.</p>
            {skipWarn ? <p className="muted">План сгенерировать можно, публикация потребует Telegram / WP / Gmail.</p> : null}
            <div className="row">
              <button className="btn" type="button" onClick={form.handleSubmit((v) => save(v, true))}>
                К каналам
              </button>
              <button
                className="btn secondary"
                type="button"
                onClick={() => {
                  setSkipWarn(true);
                  form.handleSubmit((v) => save(v, false))();
                }}
              >
                Пропустить каналы
              </button>
            </div>
          </div>
        ) : null}
        <div className="row">
          {step > 0 ? (
            <button className="btn secondary" type="button" onClick={() => setStep((n) => n - 1)}>
              Назад
            </button>
          ) : null}
          {step < 4 ? (
            <button className="btn" type="button" onClick={() => setStep((n) => n + 1)}>
              Далее
            </button>
          ) : null}
          {step === 3 ? (
            <button className="btn secondary" type="button" onClick={form.handleSubmit((v) => save(v, false))}>
              Сохранить черновик
            </button>
          ) : null}
        </div>
      </form>
    </main>
  );
}
