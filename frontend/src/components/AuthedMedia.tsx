import { useEffect, useState, type CSSProperties } from "react";
import { getSession } from "../auth/session";
import { API_PREFIX } from "../api/client";

/** <img> cannot send Bearer — fetch blob with auth and show object URL. */
export function AuthedMedia({
  mediaId,
  alt,
  className,
  style,
}: {
  mediaId: string;
  alt: string;
  className?: string;
  style?: CSSProperties;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    setSrc(null);
    setFailed(false);

    const token = getSession()?.tokens.access_token;
    if (!token) {
      setFailed(true);
      return;
    }

    (async () => {
      try {
        const response = await fetch(`${API_PREFIX}/media/${mediaId}/file`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) {
          if (!cancelled) setFailed(true);
          return;
        }
        const blob = await response.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [mediaId]);

  if (failed) {
    return <p className="muted">Не удалось загрузить превью обложки.</p>;
  }
  if (!src) {
    return <p className="muted">Загрузка превью…</p>;
  }
  return <img alt={alt} src={src} className={className} style={style} />;
}
