import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cf } from "../api/cf";
import { pollJob } from "../api/client";
import { pushRecentJob } from "../auth/session";
import { JobOverlay } from "./Status";

type FeedbackState = {
  open: boolean;
  label: string;
  status: string | null;
  error: string | null;
};

type TrackJobOptions = {
  kind?: string;
  intervalMs?: number;
  maxTicks?: number;
};

type ActionFeedbackApi = {
  trackAction: <T>(label: string, action: () => Promise<T>) => Promise<T>;
  trackJob: (
    label: string,
    start: () => Promise<{ job_id: string }>,
    options?: TrackJobOptions,
  ) => Promise<{ status: string; error: string | null; result?: Record<string, unknown> | null }>;
  close: () => void;
};

const ActionFeedbackContext = createContext<ActionFeedbackApi | null>(null);

const IDLE: FeedbackState = { open: false, label: "", status: null, error: null };

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Ошибка";
}

function jobErrorText(job: {
  error?: string | null;
  result?: Record<string, unknown> | null;
}): string | null {
  const payload = job.result?.error;
  if (payload && typeof payload === "object") {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return job.error ?? null;
}

export function ActionFeedbackProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<FeedbackState>(IDLE);
  const closeTimer = useRef<number | null>(null);

  const close = useCallback(() => {
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    setState(IDLE);
  }, []);

  useEffect(() => {
    if (state.status !== "succeeded" || !state.open) return;
    closeTimer.current = window.setTimeout(() => {
      setState(IDLE);
      closeTimer.current = null;
    }, 1400);
    return () => {
      if (closeTimer.current != null) {
        window.clearTimeout(closeTimer.current);
        closeTimer.current = null;
      }
    };
  }, [state.status, state.open]);

  const trackAction = useCallback(async <T,>(label: string, action: () => Promise<T>) => {
    setState({ open: true, label, status: "running", error: null });
    try {
      const result = await action();
      setState({ open: true, label, status: "succeeded", error: null });
      return result;
    } catch (error) {
      setState({ open: true, label, status: "failed", error: errorMessage(error) });
      throw error;
    }
  }, []);

  const trackJob = useCallback(
    async (label: string, start: () => Promise<{ job_id: string }>, options: TrackJobOptions = {}) => {
      const kind = options.kind ?? "job";
      setState({ open: true, label, status: "queued", error: null });
      try {
        const accepted = await start();
        pushRecentJob({ id: accepted.job_id, type: kind, at: new Date().toISOString() });
        const done = await pollJob(accepted.job_id, (id) => cf.job(id), {
          intervalMs: options.intervalMs ?? 700,
          maxTicks: options.maxTicks ?? 90,
          onUpdate: (job) => {
            setState({
              open: true,
              label,
              status: job.status,
              error: jobErrorText(job),
            });
          },
        });
        setState({
          open: true,
          label,
          status: done.status,
          error: jobErrorText(done),
        });
        if (done.status === "failed") {
          throw new Error(jobErrorText(done) || done.error || `${label}: ошибка`);
        }
        return done;
      } catch (error) {
        setState((prev) =>
          prev.open && prev.status === "failed"
            ? prev
            : { open: true, label, status: "failed", error: errorMessage(error) },
        );
        throw error;
      }
    },
    [],
  );

  const api = useMemo(
    () => ({ trackAction, trackJob, close }),
    [trackAction, trackJob, close],
  );

  return (
    <ActionFeedbackContext.Provider value={api}>
      {children}
      <JobOverlay
        open={state.open}
        status={state.status}
        error={state.error}
        label={state.label}
        onClose={close}
      />
    </ActionFeedbackContext.Provider>
  );
}

export function useActionFeedback(): ActionFeedbackApi {
  const ctx = useContext(ActionFeedbackContext);
  if (!ctx) {
    throw new Error("useActionFeedback must be used inside ActionFeedbackProvider");
  }
  return ctx;
}
