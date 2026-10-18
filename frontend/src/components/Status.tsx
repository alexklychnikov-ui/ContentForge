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

function jobStatusText(status: string): string {
  if (status === "queued") return "в очереди";
  if (status === "running") return "выполняется";
  if (status === "succeeded") return "готово";
  if (status === "failed") return "ошибка";
  return status;
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
      {label}: {jobStatusText(status)}
      {error ? ` — ${error}` : ""}
    </div>
  );
}

/** Centered overlay so AI feedback stays near the action, not only at page top. */
export function JobOverlay({
  open,
  status,
  error,
  label,
  onClose,
}: {
  open: boolean;
  status?: string | null;
  error?: string | null;
  label: string;
  onClose?: () => void;
}) {
  if (!open || !status) {
    return null;
  }
  const busy = status === "queued" || status === "running";
  return (
    <div className="job-overlay" role="dialog" aria-modal="true" aria-label={label}>
      <div className={`job-overlay-card job ${status}`}>
        <h3>{label}</h3>
        <p>
          {jobStatusText(status)}
          {error ? ` — ${error}` : ""}
        </p>
        {busy ? <div className="job-spinner" aria-hidden /> : null}
        {!busy && onClose ? (
          <button className="btn" type="button" onClick={onClose}>
            Закрыть
          </button>
        ) : null}
      </div>
    </div>
  );
}
