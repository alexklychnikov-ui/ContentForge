import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type {
  AnalyticsSummary,
  AuthResponse,
  BrandPublic,
  ChannelPublic,
  ExperimentPublic,
  HolidayPublic,
  JobAccepted,
  JobPublic,
  PiecePublic,
  PlanItemPublic,
  PlanPublic,
  PublicationPublic,
  RecipientPublic,
  TokenPair,
  TrendPublic,
  VariantPublic,
} from "./types";

export const cf = {
  health: () => apiGet<{ status: string }>("/health"),
  register: (body: { email: string; password: string; workspace_name: string }) =>
    apiPost<AuthResponse>("/auth/register", body, true),
  login: (body: { email: string; password: string }) =>
    apiPost<AuthResponse>("/auth/login", body, true),
  refresh: (refresh_token: string) =>
    apiPost<TokenPair>("/auth/refresh", { refresh_token }, true),
  logout: () => apiPost<void>("/auth/logout", {}),
  brands: () => apiGet<BrandPublic[]>("/brands"),
  createBrand: (body: Record<string, unknown>) => apiPost<BrandPublic>("/brands", body),
  getBrand: (id: string) => apiGet<BrandPublic>(`/brands/${id}`),
  patchBrand: (id: string, body: Record<string, unknown>) =>
    apiPatch<BrandPublic>(`/brands/${id}`, body),
  deleteBrand: (id: string) => apiDelete(`/brands/${id}`),
  generatePlan: (brandId: string, body: Record<string, unknown>) =>
    apiPost<JobAccepted>(`/brands/${brandId}/plans/generate`, body),
  plans: (brandId: string, year?: number, month?: number) => {
    const query = new URLSearchParams();
    if (year) query.set("year", String(year));
    if (month) query.set("month", String(month));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiGet<PlanPublic[]>(`/brands/${brandId}/plans${suffix}`);
  },
  getPlan: (planId: string) => apiGet<PlanPublic>(`/plans/${planId}`),
  patchPlan: (planId: string, body: { status: string }) =>
    apiPatch<PlanPublic>(`/plans/${planId}`, body),
  addPlanItem: (planId: string, body: Record<string, unknown>) =>
    apiPost<PlanItemPublic>(`/plans/${planId}/items`, body),
  patchPlanItem: (planId: string, itemId: string, body: Record<string, unknown>) =>
    apiPatch<PlanItemPublic>(`/plans/${planId}/items/${itemId}`, body),
  deletePlanItem: (planId: string, itemId: string) =>
    apiDelete(`/plans/${planId}/items/${itemId}`),
  job: (jobId: string) => apiGet<JobPublic>(`/jobs/${jobId}`),
  holidays: (year: number, month: number, brandId?: string) => {
    const query = new URLSearchParams({ year: String(year), month: String(month) });
    if (brandId) query.set("brand_id", brandId);
    return apiGet<HolidayPublic[]>(`/holidays?${query.toString()}`);
  },
  trends: (brandId: string) => apiGet<TrendPublic[]>(`/brands/${brandId}/trends`),
  addTrend: (brandId: string, body: Record<string, unknown>) =>
    apiPost<TrendPublic>(`/brands/${brandId}/trends`, body),
  content: (brandId: string) => apiGet<PiecePublic[]>(`/brands/${brandId}/content`),
  createPiece: (brandId: string, body: Record<string, unknown>) =>
    apiPost<PiecePublic>(`/brands/${brandId}/content`, body),
  getPiece: (pieceId: string) => apiGet<PiecePublic>(`/content/${pieceId}`),
  generateContent: (pieceId: string, body: Record<string, unknown>) =>
    apiPost<JobAccepted>(`/content/${pieceId}/generate`, body),
  addVariant: (pieceId: string, body: Record<string, unknown>) =>
    apiPost<VariantPublic>(`/content/${pieceId}/variants`, body),
  patchVariant: (pieceId: string, variantId: string, body: Record<string, unknown>) =>
    apiPatch<VariantPublic>(`/content/${pieceId}/variants/${variantId}`, body),
  rewrite: (pieceId: string, variantId: string, body: Record<string, unknown>) =>
    apiPost<JobAccepted>(`/content/${pieceId}/variants/${variantId}/rewrite`, body),
  channels: (brandId: string) => apiGet<ChannelPublic[]>(`/brands/${brandId}/channels`),
  saveChannel: (brandId: string, type: string, body: Record<string, unknown>) =>
    apiPost<ChannelPublic>(`/brands/${brandId}/channels/${type}/credentials`, body),
  channelHealth: (channelId: string) =>
    apiPost<{ id: string; status: string; ok: boolean; reason?: string | null }>(
      `/channels/${channelId}/health`,
    ),
  revokeChannel: (channelId: string) => apiDelete(`/channels/${channelId}`),
  recipients: (brandId: string) => apiGet<RecipientPublic[]>(`/brands/${brandId}/recipients`),
  addRecipient: (brandId: string, body: Record<string, unknown>) =>
    apiPost<RecipientPublic>(`/brands/${brandId}/recipients`, body),
  patchRecipient: (id: string, body: Record<string, unknown>) =>
    apiPatch<RecipientPublic>(`/recipients/${id}`, body),
  deleteRecipient: (id: string) => apiDelete(`/recipients/${id}`),
  publications: (brandId: string, status?: string) => {
    const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
    return apiGet<PublicationPublic[]>(`/brands/${brandId}/publications${suffix}`);
  },
  schedule: (brandId: string, body: Record<string, unknown>) =>
    apiPost<PublicationPublic>(`/brands/${brandId}/publications`, body),
  cancelPublication: (id: string) => apiPost<PublicationPublic>(`/publications/${id}/cancel`),
  retryPublication: (id: string) => apiPost<PublicationPublic>(`/publications/${id}/retry`),
  markManual: (id: string, body: Record<string, unknown>) =>
    apiPost<PublicationPublic>(`/publications/${id}/mark-manual`, body),
  analytics: (brandId: string, from: string, to: string) =>
    apiGet<AnalyticsSummary>(
      `/brands/${brandId}/analytics/summary?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    ),
  experiments: (brandId: string) => apiGet<ExperimentPublic[]>(`/brands/${brandId}/experiments`),
  createExperiment: (brandId: string, body: Record<string, unknown>) =>
    apiPost<ExperimentPublic>(`/brands/${brandId}/experiments`, body),
  getExperiment: (id: string) => apiGet<ExperimentPublic>(`/experiments/${id}`),
  startExperiment: (id: string) => apiPost<ExperimentPublic>(`/experiments/${id}/start`),
  stopExperiment: (id: string) => apiPost<ExperimentPublic>(`/experiments/${id}/stop`),
  winnerExperiment: (id: string, variant_id: string) =>
    apiPost<ExperimentPublic>(`/experiments/${id}/winner`, { variant_id }),
};
