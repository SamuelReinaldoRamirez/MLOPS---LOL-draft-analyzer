import type { Role } from "@/lib/api";

/**
 * Cohesive inline role glyphs. Each draws the Rift "map cell" with a position
 * marker placed where that role lives — top-left lane (top), center (jungle),
 * the mid diagonal, bottom-right lane (ADC), and a protective shield (support).
 * Uses `currentColor` so it tints to the team/accent color of its context.
 */
export default function RoleIcon({
  role,
  className = "h-4 w-4",
}: {
  role: Role;
  className?: string;
}) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <rect
        x="3.5"
        y="3.5"
        width="17"
        height="17"
        rx="4.5"
        stroke="currentColor"
        strokeWidth="1.5"
        opacity="0.32"
      />
      {role === "top" && (
        <rect x="5.5" y="5.5" width="7" height="7" rx="2" fill="currentColor" />
      )}
      {role === "jungle" && (
        <path d="M12 8.2 15.8 12 12 15.8 8.2 12z" fill="currentColor" />
      )}
      {role === "mid" && (
        <path
          d="M7.5 16.5 16.5 7.5"
          stroke="currentColor"
          strokeWidth="2.6"
          strokeLinecap="round"
        />
      )}
      {role === "adc" && (
        <rect x="11.5" y="11.5" width="7" height="7" rx="2" fill="currentColor" />
      )}
      {role === "support" && (
        <path
          d="M12 7.2 16.4 9v3.1c0 2.9-2 4.3-4.4 5.2-2.4-.9-4.4-2.3-4.4-5.2V9z"
          fill="currentColor"
        />
      )}
    </svg>
  );
}
