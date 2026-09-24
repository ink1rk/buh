/** Знак продукта: три планки разной длины, как юниты стойки. */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="rgb(var(--accent))" />
      <rect x="7" y="8" width="18" height="3.2" rx="1.6" fill="rgb(var(--accent-ink))" />
      <rect
        x="7"
        y="14.4"
        width="13"
        height="3.2"
        rx="1.6"
        fill="rgb(var(--accent-ink))"
        opacity="0.82"
      />
      <rect
        x="7"
        y="20.8"
        width="8"
        height="3.2"
        rx="1.6"
        fill="rgb(var(--accent-ink))"
        opacity="0.62"
      />
    </svg>
  );
}
