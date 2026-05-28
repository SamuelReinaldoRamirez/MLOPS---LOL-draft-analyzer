"use client";

import { useEffect, useState } from "react";

interface ChampionAvatarProps {
  /** Champion square image URL, or null/empty to show the placeholder. */
  src?: string | null;
  alt: string;
  /** Rendered size in pixels (square). */
  size?: number;
  /** Extra classes on the wrapper — typically a team-colored ring + rounding. */
  className?: string;
}

/**
 * A champion portrait that degrades gracefully: while there's no usable image
 * (empty pick, unknown champion, or a 404 from the CDN) it shows an on-theme
 * faceted-gem placeholder instead of a broken-image icon. Reused by the draft
 * picker, match history, per-game and live views for one consistent look.
 */
export default function ChampionAvatar({
  src,
  alt,
  size = 40,
  className = "rounded-lg",
}: ChampionAvatarProps) {
  const [failed, setFailed] = useState(false);

  // A new src is a fresh chance to load — clear any prior error.
  useEffect(() => setFailed(false), [src]);

  const showImage = Boolean(src) && !failed;

  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center overflow-hidden bg-surface-2 ${className}`}
      style={{ width: size, height: size }}
    >
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src as string}
          alt={alt}
          width={size}
          height={size}
          loading="lazy"
          onError={() => setFailed(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        <svg
          viewBox="0 0 24 24"
          className="h-1/2 w-1/2 text-ink-dim/60"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M12 3 20 7.5v9L12 21 4 16.5v-9z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </span>
  );
}
