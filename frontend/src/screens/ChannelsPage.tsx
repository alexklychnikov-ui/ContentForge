import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cf } from "../api/cf";
import type { BrandPublic, ChannelPublic } from "../api/types";
import { EmptyState, ErrorBanner } from "../components/Status";
import { CHANNEL_LABELS, CHANNEL_STATUS, MVP_CHANNELS, label } from "../labels";

type Shell = { brand: BrandPublic | null };

const SECRET_KEYS = ["bot_token", "app_password", "access_token", "refresh_token", "token"];

type LastHealthCheck = {
  ok: boolean;
  reason: string | null;
  at: string;
};

function isRevokedChannel(row: ChannelPublic): boolean {
  return row.status === "revoked" || Boolean(row.revoked_at);
}

function formatCheckClock(date = new Date()): string {
  return date.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function healthErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Ошибка проверки";
}

export function ChannelsPage() {
  const { brand } = useOutletContext<Shell>();
  const queryClient = useQueryClient();
  const [type, setType] = useState<(typeof MVP_CHANNELS)[number]>("telegram");
  const [form, setForm] = useState<Record<string, string>>({ display_name: "", pdn: "1" });
  const [formKey, setFormKey] = useState(0);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [oauthBanner, setOauthBanner] = useState<string | null>(null);
  const [lastChecks, setLastChecks] = useState<Record<string, LastHealthCheck>>({});

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ok = params.get("oauth");
    const err = params.get("oauth_error");
    if (ok === "instagram_ok") {
      setOauthBanner("Instagram подключён через Facebook.");
      queryClient.invalidateQueries({ queryKey: ["channels"] });
    } else if (err) {
      setOauthBanner(`OAuth: ${err}`);
    }
    if (ok || err) {
      params.delete("oauth");
      params.delete("oauth_error");
      const suffix = params.toString();
      const next = `${window.location.pathname}${suffix ? `?${suffix}` : ""}`;
      window.history.replaceState({}, "", next);
    }
  }, [queryClient]);

  const instagramOAuth = useMutation({
    mutationFn: () => cf.instagramOAuthStart(brand!.id),
    onSuccess: (data) => {
      window.location.href = data.auth_url;
    },
  });

  const channelsQuery = useQuery({
    queryKey: ["channels", brand?.id],
    queryFn: () => cf.channels(brand!.id),
    enabled: Boolean(brand),
  });
  const recipientsQuery = useQuery({
    queryKey: ["recipients", brand?.id],
    queryFn: () => cf.recipients(brand!.id),
    enabled: Boolean(brand),
  });

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        pdn_consent: form.pdn === "1",
        display_name: form.display_name || type,
      };
      if (type === "telegram") {
        body.bot_token = form.bot_token;
        body.channel_id = form.channel_id;
      }
      if (type === "gmail") {
        body.from_email = form.from_email;
        body.app_password = form.app_password;
      }
      return cf.saveChannel(brand!.id, type, body);
    },
    onSuccess: () => {
      setForm({ display_name: "", pdn: "1" });
      setFormKey((n) => n + 1);
      queryClient.invalidateQueries({ queryKey: ["channels"] });
    },
  });
  const health = useMutation({
    mutationFn: (id: string) => cf.channelHealth(id),
    onSuccess: (data, id) => {
      queryClient.invalidateQueries({ queryKey: ["channels"] });
      setLastChecks((prev) => ({
        ...prev,
        [id]: { ok: data.ok, reason: data.reason ?? null, at: formatCheckClock() },
      }));
    },
    onError: (error, id) => {
      setLastChecks((prev) => ({
        ...prev,
        [id]: { ok: false, reason: healthErrorMessage(error), at: formatCheckClock() },
      }));
    },
  });
  const adapterHealthError =
    health.isSuccess && health.data && !health.data.ok
      ? health.data.reason || "Проверка канала не прошла"
      : null;
  const revoke = useMutation({
    mutationFn: (id: string) => cf.revokeChannel(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["channels"] }),
  });
  const addRecipient = useMutation({
    mutationFn: () => cf.addRecipient(brand!.id, { email, name }),
    onSuccess: () => {
      setEmail("");
      setName("");
      queryClient.invalidateQueries({ queryKey: ["recipients"] });
    },
  });
  const removeRecipient = useMutation({
    mutationFn: (id: string) => cf.deleteRecipient(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recipients"] }),
  });

  if (!brand) {
    return (
      <main className="page">
        <EmptyState title="Нет бренда" hint="Сначала онбординг." cta="Онбординг" to="/onboarding" />
      </main>
    );
  }

  const channels = (channelsQuery.data ?? []).filter((row) => !isRevokedChannel(row));
  const leaked = channels.some((row) =>
    SECRET_KEYS.some((key) => key in (row.meta || {}) || key in row),
  );

  return (
    <main className="page grid">
      <h1>Каналы</h1>
      <p className="muted">Instagram App Review, Reels и Mailchimp не входят в MVP. Токены в GET не показываем.</p>
      {leaked ? <div className="error">В ответе каналов есть секрет — это баг API.</div> : null}
      <ErrorBanner error={channelsQuery.error || save.error || health.error || revoke.error || recipientsQuery.error || addRecipient.error || removeRecipient.error || instagramOAuth.error} />
      {oauthBanner ? <div className="job succeeded">{oauthBanner}</div> : null}
      {adapterHealthError ? <div className="error">{adapterHealthError}</div> : null}
      <div className="cards">
        {channels.map((row) => {
          const checking = health.isPending && health.variables === row.id;
          const last = lastChecks[row.id];
          const metaReason = typeof row.meta?.health_reason === "string" ? row.meta.health_reason : "";
          return (
          <div className="card" key={row.id}>
            <h3>{row.display_name}</h3>
            <p>
              {label(CHANNEL_LABELS, row.type)} · {label(CHANNEL_STATUS, row.status)}
            </p>
            {checking ? <p className="muted">Проверка…</p> : null}
            {last && !checking ? (
              <p className={last.ok ? "muted" : "error"}>
                {last.ok ? "Проверено: ок" : "Проверено: ошибка"}
                {last.reason ? ` — ${last.reason}` : ""}
                {` · проверено ${last.at}`}
              </p>
            ) : null}
            {!last && !checking && metaReason ? <p className="muted">{metaReason}</p> : null}
            <p className="muted">истекает: {row.token_expires_at ?? "—"}</p>
            {isRevokedChannel(row) ? null : (
              <div className="row">
                <button
                  className="btn secondary"
                  type="button"
                  disabled={checking}
                  onClick={() => health.mutate(row.id)}
                >
                  {checking ? "Проверка…" : "Проверить"}
                </button>
                <button className="btn danger" type="button" onClick={() => revoke.mutate(row.id)}>
                  Revoke
                </button>
              </div>
            )}
          </div>
          );
        })}
      </div>
      {channels.length === 0 ? (
        <EmptyState title="Каналы не подключены" hint="Подключите Telegram или Gmail." cta="Онбординг" to="/onboarding" />
      ) : null}
      <form
        key={formKey}
        className="panel grid"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <h3>Подключить</h3>
        <label className="field">
          Тип
          <select value={type} onChange={(e) => setType(e.target.value as typeof type)}>
            {MVP_CHANNELS.map((item) => (
              <option key={item} value={item}>
                {label(CHANNEL_LABELS, item)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Имя
          <input value={form.display_name} onChange={(e) => setForm((p) => ({ ...p, display_name: e.target.value }))} />
        </label>
        {type === "telegram" ? (
          <>
            <label className="field">
              Bot token
              <input
                name="telegram_bot_token"
                type="password"
                autoComplete="off"
                value={form.bot_token ?? ""}
                onChange={(e) => {
                  save.reset();
                  setForm((p) => ({ ...p, bot_token: e.target.value }));
                }}
              />
            </label>
            <label className="field">
              Channel id
              <input
                name="telegram_channel_id"
                autoComplete="off"
                placeholder="@mychannel, -100… или -5477113632"
                value={form.channel_id ?? ""}
                onChange={(e) => {
                  save.reset();
                  setForm((p) => ({ ...p, channel_id: e.target.value }));
                }}
              />
            </label>
          </>
        ) : null}
        {type === "gmail" ? (
          <>
            <label className="field">
              From email
              <input onChange={(e) => setForm((p) => ({ ...p, from_email: e.target.value }))} />
            </label>
            <label className="field">
              App password
              <input
                type="password"
                autoComplete="off"
                onChange={(e) => setForm((p) => ({ ...p, app_password: e.target.value }))}
              />
            </label>
          </>
        ) : null}
        <label>
          <input type="checkbox" checked={form.pdn === "1"} onChange={(e) => setForm((p) => ({ ...p, pdn: e.target.checked ? "1" : "0" }))} />{" "}
          Согласие на обработку ПДн
        </label>
        <button className="btn" type="submit">
          Сохранить канал
        </button>
      </form>
      <div className="panel grid">
        <h3>Instagram</h3>
        <p className="muted">
          Professional (Creator) + Facebook Page. OAuth redirect:{" "}
          <code>/api/v1/channels/oauth/callback</code>. Пока на сервере нет META_APP_SECRET — вход
          в Facebook откроется, но callback не завершится.
        </p>
        <label>
          <input type="checkbox" checked={form.pdn === "1"} onChange={(e) => setForm((p) => ({ ...p, pdn: e.target.checked ? "1" : "0" }))} />{" "}
          Согласие на обработку ПДн
        </label>
        <button
          className="btn"
          type="button"
          disabled={form.pdn !== "1" || instagramOAuth.isPending}
          onClick={() => instagramOAuth.mutate()}
        >
          {instagramOAuth.isPending ? "Переход в Facebook…" : "Подключить через Facebook"}
        </button>
      </div>
      <div className="panel grid">
        <h3>Получатели Gmail</h3>
        <div className="row">
          <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input placeholder="имя" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn" type="button" onClick={() => addRecipient.mutate()}>
            Добавить
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Имя</th>
              <th>Статус</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(recipientsQuery.data ?? []).map((row) => (
              <tr key={row.id}>
                <td>{row.email}</td>
                <td>{row.name}</td>
                <td>{row.status}</td>
                <td>
                  <button
                    className="btn"
                    type="button"
                    disabled={removeRecipient.isPending}
                    onClick={() => removeRecipient.mutate(row.id)}
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
