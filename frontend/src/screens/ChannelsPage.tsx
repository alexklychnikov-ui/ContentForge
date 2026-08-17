import { useState } from "react";
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
  const [lastChecks, setLastChecks] = useState<Record<string, LastHealthCheck>>({});

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
      if (type === "wordpress") {
        body.site_url = form.site_url;
        body.username = form.username;
        body.app_password = form.app_password;
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
      <ErrorBanner error={channelsQuery.error || save.error || health.error || revoke.error || recipientsQuery.error} />
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
        <EmptyState title="Каналы не подключены" hint="Подключите Telegram, WordPress или Gmail." cta="Онбординг" to="/onboarding" />
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
                onChange={(e) => setForm((p) => ({ ...p, bot_token: e.target.value }))}
              />
            </label>
            <label className="field">
              Channel id
              <input
                name="telegram_channel_id"
                autoComplete="off"
                placeholder="@mychannel или -100…"
                onChange={(e) => setForm((p) => ({ ...p, channel_id: e.target.value }))}
              />
            </label>
          </>
        ) : null}
        {type === "wordpress" ? (
          <>
            <label className="field">
              Site URL
              <input onChange={(e) => setForm((p) => ({ ...p, site_url: e.target.value }))} />
            </label>
            <label className="field">
              Username
              <input onChange={(e) => setForm((p) => ({ ...p, username: e.target.value }))} />
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
            </tr>
          </thead>
          <tbody>
            {(recipientsQuery.data ?? []).map((row) => (
              <tr key={row.id}>
                <td>{row.email}</td>
                <td>{row.name}</td>
                <td>{row.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
