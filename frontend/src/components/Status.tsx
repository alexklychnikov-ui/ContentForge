import { Link } from "react-router-dom";

type Props = {
  title: string;
  hint: string;
  cta: string;
  to: string;
};

export function EmptyState({ title, hint, cta, to }: Props) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <p>{hint}</p>
      <Link className="btn" to={to}>
        {cta}
      </Link>
    </div>
  );
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) {
    return null;
  }
  const message = error instanceof Error ? error.message : "Ошибка";
  return <div className="error">{message}</div>;
}

export function JobBanner({
  status,
  error,
  label,
}: {
  status?: string | null;
  error?: string | null;
  label: string;
}) {
  if (!status) {
    return null;
  }
  return (
    <div className={`job ${status}`} role="status">
      {label}: {status === "queued" ? "в очереди" : status === "running" ? "выполняется" : status === "succeeded" ? "готово" : "ошибка"}
      {error ? ` — ${error}` : ""}
    </div>
  );
}
