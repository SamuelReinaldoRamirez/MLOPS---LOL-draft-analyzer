"use client";

/**
 * Standard inline error/notice with an optional one-click retry — the recovery
 * path for transient failures (e.g. a momentary Riot upstream 502). `tone`
 * "error" is the loud red box for blocking failures; "muted" is the quiet
 * surface box for non-blocking sections (e.g. the timeline).
 */
export default function ErrorState({
  message,
  onRetry,
  tone = "error",
  role = "alert",
}: {
  message: string;
  onRetry?: () => void;
  tone?: "error" | "muted";
  role?: "alert" | "status";
}) {
  const isError = tone === "error";
  return (
    <div
      role={role}
      className={`rounded-xl border px-4 py-3.5 text-sm ${
        isError
          ? "border-team_red/40 bg-team_red/10 text-team_red-glow"
          : "border-line bg-surface-2/60 text-ink-soft"
      }`}
    >
      <p className="text-pretty">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className={`mt-2.5 inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
            isError
              ? "border-team_red/40 text-team_red-glow hover:bg-team_red/15"
              : "border-line-strong text-ink-soft hover:bg-surface-3 hover:text-ink"
          }`}
        >
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" aria-hidden="true">
            <path
              d="M20 11a8 8 0 1 0-.7 3.3M20 5v6h-6"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Try again
        </button>
      )}
    </div>
  );
}
