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
