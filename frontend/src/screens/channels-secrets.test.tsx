import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { applyAuth } from "../auth/session";
import type { BrandPublic } from "../api/types";
import { ChannelsPage } from "./ChannelsPage";

const brand: BrandPublic = {
  id: "brand-1",
  workspace_id: "ws-1",
  name: "N",
  niche: "n",
  audience: "a",
  voice_tone: "v",
  stopwords: [],
  offers: ["o"],
  example_posts: [],
  default_locale: "ru",
  timezone: "Europe/Moscow",
  onboarding_completed_at: "2026-01-01T00:00:00Z",
  onboarding_completed: true,
  created_at: "2026-01-01T00:00:00Z",
};

const LEAK = "123:LEAKED-BOT-TOKEN";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  };
}

function renderChannels() {
  applyAuth({
    user: { id: "u1", email: "a@b.c", is_active: true, created_at: "2026-01-01T00:00:00Z" },
    workspace: {
      id: "ws-1",
      name: "W",
      created_at: "2026-01-01T00:00:00Z",
      openai_soft_quota_tokens: null,
      role: "owner",
    },
    tokens: { access_token: "jwt-acc", refresh_token: "jwt-ref", token_type: "bearer", expires_in: 900 },
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Routes>
          <Route element={<Outlet context={{ brand }} />}>
            <Route index element={<ChannelsPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SCR-CHN secrets", () => {
  it("does not render bot_token from GET meta and keeps connect inputs as password", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = String(url);
        if (path.includes("/channels")) {
          return jsonResponse([
            {
              id: "ch-1",
              brand_id: "brand-1",
              type: "telegram",
              display_name: "TG",
              status: "connected",
              scopes: [],
              token_expires_at: null,
              external_account_id: null,
              meta: { bot_token: LEAK, app_password: "wp-app-pass-LEAK" },
              revoked_at: null,
            },
          ]);
        }
        return jsonResponse([]);
      }),
    );
    renderChannels();
    expect(await screen.findByText(/секрет/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(LEAK);
    expect(document.body.textContent).not.toContain("wp-app-pass-LEAK");
    expect(screen.getByLabelText("Bot token")).toHaveAttribute("type", "password");
    expect(screen.queryByText("Viewer")).toBeNull();
  });

  it("hides revoked channels and does not show Проверить/Revoke on them", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = String(url);
        if (path.includes("/channels")) {
          return jsonResponse([
            {
              id: "ch-live",
              brand_id: "brand-1",
              type: "telegram",
              display_name: "Live TG",
              status: "connected",
              scopes: [],
              token_expires_at: null,
              external_account_id: null,
              meta: {},
              revoked_at: null,
            },
            {
              id: "ch-dead",
              brand_id: "brand-1",
              type: "telegram",
              display_name: "Dead TG",
              status: "revoked",
              scopes: [],
              token_expires_at: null,
              external_account_id: null,
              meta: {},
              revoked_at: "2026-08-17T00:00:00Z",
            },
          ]);
        }
        return jsonResponse([]);
      }),
    );
    renderChannels();
    expect(await screen.findByText("Live TG")).toBeInTheDocument();
    expect(screen.queryByText("Dead TG")).toBeNull();
    expect(screen.queryByText("отозван")).toBeNull();
    expect(screen.getAllByRole("button", { name: "Проверить" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Revoke" })).toHaveLength(1);
  });

  it("shows Проверка… while health is pending and Проверено: ок after success", async () => {
    const user = userEvent.setup();
    let releaseHealth: (() => void) | undefined;
    const healthGate = new Promise<void>((resolve) => {
      releaseHealth = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const path = String(url);
        if (path.includes("/channels/") && path.includes("/health") && init?.method === "POST") {
          await healthGate;
          return jsonResponse({
            id: "ch-live",
            status: "connected",
            ok: true,
            reason: "getMe ok via=proxy",
          });
        }
        if (path.includes("/channels")) {
          return jsonResponse([
            {
              id: "ch-live",
              brand_id: "brand-1",
              type: "telegram",
              display_name: "Сергей",
              status: "connected",
              scopes: [],
              token_expires_at: null,
              external_account_id: null,
              meta: {},
              revoked_at: null,
            },
          ]);
        }
        return jsonResponse([]);
      }),
    );
    renderChannels();
    expect(await screen.findByText("Сергей")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    const pending = await screen.findByRole("button", { name: "Проверка…" });
    expect(pending).toBeDisabled();
    expect(screen.getAllByText("Проверка…").length).toBeGreaterThanOrEqual(2);
    releaseHealth?.();
    expect(await screen.findByText(/Проверено: ок/)).toBeInTheDocument();
    expect(screen.getByText(/getMe ok via=proxy/)).toBeInTheDocument();
    expect(screen.getByText(/проверено /)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Проверить" })).toBeEnabled();
    });
  });

  it("shows ErrorBanner and per-card reason when health HTTP fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const path = String(url);
        if (path.includes("/channels/") && path.includes("/health") && init?.method === "POST") {
          return jsonResponse(
            { error: { code: "adapter_error", message: "Нет связи с API", details: {} } },
            502,
          );
        }
        if (path.includes("/channels")) {
          return jsonResponse([
            {
              id: "ch-live",
              brand_id: "brand-1",
              type: "telegram",
              display_name: "Сергей",
              status: "connected",
              scopes: [],
              token_expires_at: null,
              external_account_id: null,
              meta: {},
              revoked_at: null,
            },
          ]);
        }
        return jsonResponse([]);
      }),
    );
    renderChannels();
    expect(await screen.findByText("Сергей")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    expect(await screen.findByText("Нет связи с API")).toBeInTheDocument();
    expect(screen.getByText(/Проверено: ошибка/)).toBeInTheDocument();
    expect(screen.getAllByText(/Нет связи с API/).length).toBeGreaterThanOrEqual(2);
  });

  it("shows banner and card error when adapter health returns ok=false", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const path = String(url);
        if (path.includes("/channels/") && path.includes("/health") && init?.method === "POST") {
          return jsonResponse({
            id: "ch-live",
            status: "error",
            ok: false,
            reason: "Нет связи с api.telegram.org. via=proxy",
          });
        }
        if (path.includes("/channels")) {
          return jsonResponse([
            {
              id: "ch-live",
              brand_id: "brand-1",
              type: "telegram",
              display_name: "Сергей",
              status: "connected",
              scopes: [],
              token_expires_at: null,
              external_account_id: null,
              meta: { health_reason: "Нет связи с api.telegram.org. via=direct" },
              revoked_at: null,
            },
          ]);
        }
        return jsonResponse([]);
      }),
    );
    renderChannels();
    expect(await screen.findByText("Сергей")).toBeInTheDocument();
    expect(screen.getByText(/via=direct/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    expect(await screen.findByText(/Проверено: ошибка/)).toBeInTheDocument();
    expect(screen.getAllByText(/via=proxy/).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/via=direct/)).toBeNull();
  });
});
