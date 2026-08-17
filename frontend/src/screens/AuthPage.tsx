import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { cf } from "../api/cf";
import { ApiError } from "../api/client";
import { applyAuth } from "../auth/session";
import { ErrorBanner } from "../components/Status";

const loginSchema = z.object({
  email: z.string().email("Укажите email"),
  password: z.string().min(1, "Укажите пароль"),
});

const registerSchema = loginSchema.extend({
  password: z.string().min(8, "Минимум 8 символов"),
  workspace_name: z.string().min(1, "Название воркспейса"),
});

type LoginValues = z.infer<typeof loginSchema>;
type RegisterValues = z.infer<typeof registerSchema>;

export function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [apiError, setApiError] = useState<unknown>(null);
  const loginForm = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });
  const registerForm = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  async function onLogin(values: LoginValues) {
    setApiError(null);
    try {
      const payload = await cf.login(values);
      applyAuth(payload);
      navigate("/");
    } catch (error) {
      setApiError(error);
    }
  }

  async function onRegister(values: RegisterValues) {
    setApiError(null);
    try {
      const payload = await cf.register(values);
      applyAuth(payload);
      navigate("/onboarding");
    } catch (error) {
      setApiError(error);
    }
  }

  const invalid =
    apiError instanceof ApiError && apiError.code === "invalid_credentials"
      ? apiError.message
      : apiError instanceof ApiError && apiError.code === "email_taken"
        ? `${apiError.message}. Войдите, если аккаунт уже есть.`
        : null;

  return (
    <main className="auth-box panel">
      <div className="brand-mark">NODEX</div>
      <h1>ContentForge</h1>
      <p className="muted">Вход в рабочее пространство</p>
      <div className="row">
        <button
          type="button"
          className={`btn ${mode === "login" ? "" : "secondary"}`}
          onClick={() => setMode("login")}
        >
          Вход
        </button>
        <button
          type="button"
          className={`btn ${mode === "register" ? "" : "secondary"}`}
          onClick={() => setMode("register")}
        >
          Регистрация
        </button>
      </div>
      {invalid ? (
        <div className="error" data-testid="auth-error">
          {invalid}
        </div>
      ) : (
        <ErrorBanner error={apiError} />
      )}
      {mode === "login" ? (
        <form className="grid" onSubmit={loginForm.handleSubmit(onLogin)}>
          <label className="field">
            Email
            <input type="email" {...loginForm.register("email")} />
          </label>
          <label className="field">
            Пароль
            <input type="password" {...loginForm.register("password")} />
          </label>
          <button className="btn" type="submit" disabled={loginForm.formState.isSubmitting}>
            Войти
          </button>
        </form>
      ) : (
        <form className="grid" onSubmit={registerForm.handleSubmit(onRegister)}>
          <label className="field">
            Email
            <input type="email" {...registerForm.register("email")} />
          </label>
          <label className="field">
            Пароль
            <input type="password" {...registerForm.register("password")} />
          </label>
          <label className="field">
            Воркспейс
            <input {...registerForm.register("workspace_name")} />
          </label>
          <button className="btn" type="submit" disabled={registerForm.formState.isSubmitting}>
            Создать аккаунт
          </button>
        </form>
      )}
    </main>
  );
}
