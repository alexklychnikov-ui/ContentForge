import { useEffect, useState, type CSSProperties } from "react";
import { getSession } from "../auth/session";
import { API_PREFIX } from "../api/client";

/** <img> cannot send Bearer — fetch blob with auth and show object URL. */
export function AuthedMedia({
  mediaId,
  alt,
  className,
  style,
  zoomable = false,
}: {
  mediaId: string;
  alt: string;
  className?: string;
  style?: CSSProperties;
  zoomable?: boolean;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [zoomed, setZoomed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    setSrc(null);
    setFailed(false);
    setZoomed(false);

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

  useEffect(() => {
    if (!zoomed) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setZoomed(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomed]);

  if (failed) {
    return <p className="muted">Не удалось загрузить превью обложки.</p>;
  }
  if (!src) {
    return <p className="muted">Загрузка превью…</p>;
  }

  return (
    <>
      <button
        type="button"
        className={`media-thumb${zoomable ? " zoomable" : ""}`}
        onClick={() => {
          if (zoomable) setZoomed(true);
        }}
        disabled={!zoomable}
        aria-label={zoomable ? "Увеличить изображение" : alt}
      >
        <img alt={alt} src={src} className={className} style={style} />
      </button>
      {zoomed ? (
        <div
          className="media-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label={alt}
          onClick={() => setZoomed(false)}
        >
          <img
            alt={alt}
            src={src}
            className="media-lightbox-img"
            onClick={(event) => event.stopPropagation()}
          />
          <button className="btn media-lightbox-close" type="button" onClick={() => setZoomed(false)}>
            Закрыть
          </button>
        </div>
      ) : null}
    </>
  );
}
