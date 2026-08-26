export type ErrorEnvelope = {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type UserPublic = {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
};

export type WorkspacePublic = {
  id: string;
  name: string;
  created_at: string;
  openai_soft_quota_tokens: number | null;
  role: string | null;
};

export type AuthResponse = {
  user: UserPublic;
  workspace: WorkspacePublic;
  tokens: TokenPair;
};

export type BrandPublic = {
  id: string;
  workspace_id: string;
  name: string;
  niche: string;
  audience: string;
  voice_tone: string;
  stopwords: string[];
  offers: string[];
  example_posts: string[];
  default_locale: "ru" | "en";
  timezone: string;
  onboarding_completed_at: string | null;
  onboarding_completed: boolean;
  created_at: string;
};

export type JobAccepted = { job_id: string };

export type JobPublic = {
  id: string;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed";
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
};

export type PlanItemPublic = {
  id: string;
  plan_id: string;
  date: string;
  channel_type: string;
  content_type: string;
  theme: string;
  goal: string;
  hook: string;
  content_piece_id: string | null;
  sort_order: number;
};

export type PlanPublic = {
  id: string;
  brand_id: string;
  year: number;
  month: number;
  status: "generating" | "draft" | "approved" | "archived";
  params: Record<string, unknown>;
  model: string;
  created_by: string;
  created_at: string;
  items: PlanItemPublic[];
};

export type VariantPublic = {
  id: string;
  piece_id: string;
  label: string;
  payload: Record<string, unknown>;
  revision: number;
  is_immutable: boolean;
};

export type PiecePublic = {
  id: string;
  brand_id: string;
  type: "social_post" | "article" | "email";
  locale: "ru" | "en";
  status: string;
  plan_item_id: string | null;
  stopword_override: boolean;
  created_at: string;
  variants: VariantPublic[];
};

export type ChannelPublic = {
  id: string;
  brand_id: string;
  type: string;
  display_name: string;
  status: string;
  scopes: string[];
  token_expires_at: string | null;
  external_account_id: string | null;
  meta: Record<string, unknown>;
  revoked_at: string | null;
};

export type PublicationPublic = {
  id: string;
  variant_id: string;
  channel_account_id: string;
  scheduled_at: string;
  status: string;
  external_id: string | null;
  external_url: string | null;
  error_code: string | null;
  error_message: string | null;
  attempt_count: number;
  idempotency_key: string | null;
  experiment_id: string | null;
  published_at: string | null;
  meta: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  channel_type: string;
  channel_display_name?: string | null;
  piece_id?: string | null;
};

export type HolidayPublic = {
  id: string;
  date: string;
  name: string;
  country: string;
  source: string;
  brand_id: string | null;
};

export type TrendPublic = {
  id: string;
  brand_id: string | null;
  title: string;
  note: string;
  starts_on: string | null;
  ends_on: string | null;
  status: string;
  source: string;
};

export type RecipientPublic = {
  id: string;
  brand_id: string;
  email: string;
  name: string | null;
  status: string;
  source: string;
};

export type ExperimentPublic = {
  id: string;
  piece_id: string;
  variant_a_id: string;
  variant_b_id: string;
  channel_type: string;
  mode: string;
  primary_metric: string;
  window_start: string;
  window_end: string;
  schedule_a: string;
  schedule_b: string;
  status: string;
  winner_variant_id: string | null;
  created_at: string;
  metrics: Record<string, unknown> | null;
};

export type AnalyticsChannel = {
  channel_type: string;
  publications: number;
  failed: number;
  availability: string;
  metrics: Record<string, { sum: number; avg: number; availability: string }>;
};

export type AnalyticsSummary = {
  from: string;
  to: string;
  channels: AnalyticsChannel[];
};
