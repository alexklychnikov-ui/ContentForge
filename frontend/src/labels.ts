export const CHANNEL_LABELS: Record<string, string> = {
  telegram: "Telegram",
  wordpress: "WordPress",
  gmail: "Gmail",
  vk: "VK",
  instagram: "Instagram",
};

export const CONTENT_LABELS: Record<string, string> = {
  social_post: "Пост",
  article: "Статья",
  email: "Письмо",
};

export const PIECE_STATUS: Record<string, string> = {
  draft: "черновик",
  ready: "готов",
  archived: "архив",
};

export type FieldMeta = { label: string; required?: boolean; hint?: string };

export const FIELD_META: Record<string, Record<string, FieldMeta>> = {
  social_post: {
    text: { label: "Текст поста", required: true },
    cta: { label: "Призыв к действию (CTA)", hint: "по желанию" },
    hashtags: { label: "Хештеги", hint: "по желанию, через пробел" },
    alt_text: { label: "Подпись к картинке (alt)", hint: "по желанию" },
  },
  article: {
    title: { label: "Заголовок", required: true },
    slug: { label: "URL-slug", hint: "по желанию" },
    excerpt: { label: "Краткое описание", hint: "по желанию" },
    body_markdown: { label: "Текст статьи", required: true },
    seo_title: { label: "SEO-заголовок", hint: "по желанию" },
    seo_description: { label: "SEO-описание", hint: "по желанию" },
  },
  email: {
    subject: { label: "Тема письма", required: true },
    preheader: { label: "Прехедер", hint: "по желанию" },
    body_markdown: { label: "Текст письма", required: true },
  },
};

export const TYPE_FIELD_BLURB: Record<string, string> = {
  social_post: "Для TG/VK нужен Текст. CTA и хештеги — по желанию.",
  article: "Нужны Заголовок и Текст статьи. Остальное — по желанию.",
  email: "Нужны Тема и Текст письма. Прехедер — по желанию.",
};

export const PLAN_STATUS: Record<string, string> = {
  generating: "генерация",
  draft: "черновик",
  approved: "утверждён",
  archived: "архив",
};

export const PUB_STATUS: Record<string, string> = {
  draft: "черновик",
  scheduled: "в очереди",
  publishing: "публикуется",
  published: "опубликован",
  published_manual: "вручную",
  failed: "ошибка",
  dead: "dead",
  cancelled: "отменён",
};

export const CHANNEL_STATUS: Record<string, string> = {
  connected: "подключён",
  expired: "истёк",
  missing_scopes: "нет прав",
  error: "ошибка",
  revoked: "отозван",
};

export const MVP_CHANNELS = ["telegram", "vk", "gmail"] as const;

/** IANA ids; RU/CIS first. */
export const TIMEZONE_OPTIONS: { value: string; label: string }[] = [
  { value: "Europe/Kaliningrad", label: "Калининград (UTC+2)" },
  { value: "Europe/Moscow", label: "Москва (UTC+3)" },
  { value: "Europe/Samara", label: "Самара (UTC+4)" },
  { value: "Asia/Yekaterinburg", label: "Екатеринбург (UTC+5)" },
  { value: "Asia/Omsk", label: "Омск (UTC+6)" },
  { value: "Asia/Krasnoyarsk", label: "Красноярск (UTC+7)" },
  { value: "Asia/Irkutsk", label: "Иркутск (UTC+8)" },
  { value: "Asia/Yakutsk", label: "Якутск (UTC+9)" },
  { value: "Asia/Vladivostok", label: "Владивосток (UTC+10)" },
  { value: "Asia/Magadan", label: "Магадан (UTC+11)" },
  { value: "Asia/Kamchatka", label: "Камчатка (UTC+12)" },
  { value: "Europe/Minsk", label: "Минск (UTC+3)" },
  { value: "Europe/Kyiv", label: "Киев (UTC+2/+3)" },
  { value: "Asia/Almaty", label: "Алматы (UTC+5)" },
  { value: "Asia/Tashkent", label: "Ташкент (UTC+5)" },
  { value: "Europe/Berlin", label: "Берлин (UTC+1/+2)" },
  { value: "Europe/London", label: "Лондон (UTC+0/+1)" },
  { value: "UTC", label: "UTC" },
  { value: "America/New_York", label: "Нью-Йорк (UTC−5/−4)" },
];

export function timezoneSelectOptions(current?: string): { value: string; label: string }[] {
  const value = (current || "").trim();
  if (value && !TIMEZONE_OPTIONS.some((item) => item.value === value)) {
    return [{ value, label: value }, ...TIMEZONE_OPTIONS];
  }
  return TIMEZONE_OPTIONS;
}

export function label(map: Record<string, string>, key: string): string {
  return map[key] ?? key;
}
