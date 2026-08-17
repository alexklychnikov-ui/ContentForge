import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthPage } from "../screens/AuthPage";

describe("SCR-AUTH login", () => {
  it("shows the same invalid_credentials message", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 401,
        text: async () =>
          JSON.stringify({
            error: {
              code: "invalid_credentials",
              message: "Неверный email или пароль",
              details: {},
            },
          }),
      })),
    );
    render(
      <MemoryRouter>
        <AuthPage />
      </MemoryRouter>,
    );
    await user.type(screen.getByLabelText("Email"), "nobody@example.com");
    await user.type(screen.getByLabelText("Пароль"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    const banner = await screen.findByTestId("auth-error");
    expect(banner).toHaveTextContent("Неверный email или пароль");
    expect(banner.textContent?.toLowerCase()).not.toMatch(/exists|не найден|зарегистри/);
  });
});
