/**
 * SafeNet KZ brand mark.
 *
 * A shield (protection / law enforcement) enclosing a hub-and-spoke network —
 * the central node is the scheme organiser the platform exists to surface.
 * Monochrome (uses currentColor) so it reads on the indigo brand tile, in
 * dark mode, and as a favicon, at any size.
 */
type P = { size?: number; className?: string; style?: React.CSSProperties };

export function LogoMark({ size = 20, className, style }: P) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      style={style}
      aria-hidden="true"
      focusable="false"
    >
      {/* shield */}
      <path
        d="M12 2.6l7 2.6v5.2c0 4.6-3 8.2-7 10.4-4-2.2-7-5.8-7-10.4V5.2l7-2.6z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
        fill="none"
      />
      {/* spokes from the central hub */}
      <g stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" opacity="0.9">
        <line x1="12" y1="11" x2="8.7" y2="8.4" />
        <line x1="12" y1="11" x2="15.3" y2="8.4" />
        <line x1="12" y1="11" x2="12" y2="14.8" />
      </g>
      {/* nodes */}
      <g fill="currentColor">
        <circle cx="8.7" cy="8.4" r="1.25" />
        <circle cx="15.3" cy="8.4" r="1.25" />
        <circle cx="12" cy="14.8" r="1.25" />
      </g>
      {/* central hub — emphasised */}
      <circle cx="12" cy="11" r="1.9" fill="currentColor" />
      <circle cx="12" cy="11" r="3.1" stroke="currentColor" strokeWidth="1.1" opacity="0.45" fill="none" />
    </svg>
  );
}

/** Full lockup: monochrome mark + wordmark. Used where the brand stands alone. */
export function LogoLockup({ size = 27 }: { size?: number }) {
  return (
    <span className="brand">
      <LogoMark className="brand-mark" size={size} />
      <span>
        <span className="title">SafeNet KZ</span>
        <span className="subtitle">Цифровой щит</span>
      </span>
    </span>
  );
}
