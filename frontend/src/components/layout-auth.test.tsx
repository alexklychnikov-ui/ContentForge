import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { applyAuth, setSession } from "../auth/session";
import type { AuthResponse } from "../api/types";
import { Layout } from "./Layout";

const authPayload: AuthResponse = {
  user: { id: "u1", email: "a@b.c", is_active: true, created_at: "2026-01-01T00:00:00Z" },
  workspace: {
    id: "ws-1",
    name: "W",
    created_at: "2026-01-01T00:00:00Z",
    openai_soft_quota_tokens: null,
    role: "owner",
  },
  tokens: { access_token: "jwt-acc", refresh_token: "jwt-ref", token_type: "bearer", expires_in: 900 },
};

function renderLayout() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/login" element={<div>login-screen</div>} />
          <Route path="/" element={<Layout />}>
            <Route index element={<div>dash-screen</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("protected shell JWT", () => {
  it("does not call /brands without a session", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => "[]",
    }));
    vi.stubGlobal("fetch", fetchMock);
    renderLayout();
    expect(await screen.findByText("login-screen")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not call /brands when access_token is empty", async () => {
    setSession({
      ...authPayload,
      tokens: { ...authPayload.tokens, access_token: "" },
    });
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => "[]",
    }));
    vi.stubGlobal("fetch", fetchMock);
    renderLayout();
    expect(await screen.findByText("login-screen")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("calls /brands with Bearer when JWT is present", async () => {
    applyAuth(authPayload);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => "[]",
    }));
    vi.stubGlobal("fetch", fetchMock);
    renderLayout();
    expect(await screen.findByText("dash-screen")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(call[1].headers).get("Authorization")).toBe("Bearer jwt-acc");
  });
});
