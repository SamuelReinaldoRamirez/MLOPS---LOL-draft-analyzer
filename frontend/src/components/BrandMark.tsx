/**
 * The Hextech crystal brand glyph — a faceted gold gem used in the nav, hero,
 * and footer. Pure SVG so it scales crisply and inherits theme colors.
 */
export default function BrandMark({
  className = "h-7 w-7",
}: {
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      role="img"
      aria-label="Draft Predictor"
      fill="none"
    >
      <defs>
        <linearGradient id="bm-gold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#F0E6D2" />
          <stop offset="45%" stopColor="#C8AA6E" />
          <stop offset="100%" stopColor="#785A28" />
        </linearGradient>
      </defs>
      {/* Outer faceted hex */}
      <path
        d="M16 1.5 28.6 8.9v14.2L16 30.5 3.4 23.1V8.9z"
        stroke="url(#bm-gold)"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      {/* Inner crystal */}
      <path
        d="M16 8 22 16l-6 8-6-8z"
        fill="url(#bm-gold)"
        opacity="0.92"
      />
      <path d="M10 16h12" stroke="#0E1626" strokeWidth="1.2" opacity="0.6" />
    </svg>
  );
}
