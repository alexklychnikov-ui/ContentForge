import { describe, expect, it, vi } from "vitest";
import { applyAuth, clearSession, getSession, setSession } from "../auth/session";
import { ApiError, apiGet, apiPost, parseErrorEnvelope } from "./client";
import type { AuthResponse } from "./types";

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

function authHeader(call: unknown[]): string | null {
  const init = call[1] as RequestInit;
  return new Headers(init.headers).get("Authorization");
}

describe("API error envelope", () => {
  it("maps invalid_credentials without user enumeration fields", () => {
    const error = parseErrorEnvelope(
      {
        error: {
          code: "invalid_credentials",
          message: "Неверный email или пароль",
          details: {},
        },
      },
      401,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(401);
    expect(error.code).toBe("invalid_credentials");
    expect(error.message).toBe("Неверный email или пароль");
    expect(error.message.toLowerCase()).not.toMatch(/exists|не найден|not found|unknown|зарегистри/);
  });

  it("maps vite proxy 502/ECONNREFUSED to API down, not generic request error", () => {
    const gateway = parseErrorEnvelope("", 502);
    expect(gateway.code).toBe("network_error");
    expect(gateway.message).toBe("Нет связи с API");
    const refused = parseErrorEnvelope("http proxy error: /api/v1/brands\nECONNREFUSED", 500);
    expect(refused.code).toBe("network_error");
    expect(refused.message).toBe("Нет связи с API");
  });

  it("maps FastAPI detail 404 instead of generic request error", () => {
    const error = parseErrorEnvelope({ detail: "Not Found" }, 404);
    expect(error.code).toBe("not_found");
    expect(error.message).toBe("Not Found");
  });

  it("maps 422 validation details to a field message", () => {
    const error = parseErrorEnvelope(
      {
        error: {
          code: "validation_error",
          message: "Ошибка валидации",
          details: {
            errors: [{ loc: ["body", "password"], msg: "String should have at least 8 characters", type: "string_too_short" }],
          },
        },
      },
      422,
    );
    expect(error.code).toBe("validation_error");
    expect(error.message).toContain("password");
    expect(error.message).toContain("at least 8");
  });
});

describe("JWT on protected API", () => {
  it("sends Bearer when session has access_token", async () => {
    applyAuth(authPayload);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => "[]",
    }));
    vi.stubGlobal("fetch", fetchMock);
    await apiGet("/brands");
    expect(authHeader(fetchMock.mock.calls[0])).toBe("Bearer jwt-acc");
  });

  it("omits Authorization on skipAuth login even with a session", async () => {
    applyAuth(authPayload);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(authPayload),
    }));
    vi.stubGlobal("fetch", fetchMock);
    await apiPost("/auth/login", { email: "a@b.c", password: "x" }, true);
    expect(authHeader(fetchMock.mock.calls[0])).toBeNull();
  });

  it("does not treat empty access_token as a session", async () => {
    setSession({
      ...authPayload,
      tokens: { ...authPayload.tokens, access_token: "" },
    });
    expect(getSession()).toBeNull();
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => "[]",
    }));
    vi.stubGlobal("fetch", fetchMock);
    await apiGet("/brands");
    expect(authHeader(fetchMock.mock.calls[0])).toBeNull();
    clearSession();
  });
});
