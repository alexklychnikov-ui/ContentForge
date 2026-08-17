import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import { ApiError } from "../api/client";
import { clearSession, getBrandId, getSession, setBrandId, subscribe } from "../auth/session";
import { useEffect, useMemo, useState } from "react";

const LINKS = [
  ["/", "Дашборд"],
  ["/calendar", "Календарь"],
  ["/plan", "План"],
  ["/content", "Редактор"],
  ["/channels", "Каналы"],
  ["/queue", "Очередь"],
  ["/analytics", "Аналитика"],
  ["/ab", "A/B"],
  ["/settings", "Настройки"],
] as const;

export function Layout() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [, setTick] = useState(0);
  useEffect(() => subscribe(() => setTick((n) => n + 1)), []);
  const session = getSession();
  const selected = getBrandId();

  const brandsQuery = useQuery({
    queryKey: ["brands"],
    queryFn: cf.brands,
    enabled: Boolean(session),
  });

  const brands = brandsQuery.data ?? [];
  const current = useMemo(
    () => brands.find((item) => item.id === selected) ?? brands[0] ?? null,
    [brands, selected],
  );

  useEffect(() => {
    if (!session) {
      navigate("/login", { replace: true });
    }
  }, [session, navigate]);

  useEffect(() => {
    if (current && current.id !== selected) {
      setBrandId(current.id);
    }
  }, [current, selected]);

  if (!session) {
    return null;
  }

  const brandError =
    brandsQuery.error instanceof ApiError ? brandsQuery.error.message : brandsQuery.error?.message;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark">NODEX</div>
        <nav className="nav">
          {LINKS.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="topbar-right">
          <label className="field" style={{ minWidth: 180 }}>
            Бренд
            <select
              value={current?.id ?? ""}
              onChange={(event) => setBrandId(event.target.value || null)}
              aria-label="Переключатель бренда"
            >
              {brands.length === 0 ? <option value="">Нет брендов</option> : null}
              {brands.map((brand) => (
                <option key={brand.id} value={brand.id}>
                  {brand.name}
                  {brand.onboarding_completed ? "" : " (черновик)"}
                </option>
              ))}
            </select>
          </label>
          <span className="muted">{session.user.email}</span>
          <button
            className="btn secondary"
            type="button"
            onClick={() => {
              cf.logout().catch(() => undefined);
              clearSession();
              queryClient.clear();
              navigate("/login");
            }}
          >
            Выйти
          </button>
        </div>
      </header>
      {brandError ? <div className="error">{brandError}</div> : null}
      <Outlet context={{ brand: current, brands, brandsLoading: brandsQuery.isLoading }} />
    </div>
  );
}
