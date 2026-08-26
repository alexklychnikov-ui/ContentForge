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

export function label(map: Record<string, string>, key: string): string {
  return map[key] ?? key;
}
