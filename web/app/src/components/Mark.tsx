/** Product mark: a wellbore (line) landing on a record (dot). Not the Heirs logo. */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="1" y="1" width="30" height="30" rx="9" fill="var(--surface-2)" stroke="var(--line-strong)" />
      <path d="M11 6v11.5a4.5 4.5 0 0 0 4.5 4.5H21" fill="none" stroke="var(--text)" strokeWidth="2" strokeLinecap="round" />
      <circle cx="22.5" cy="22" r="3" fill="var(--brand)" />
    </svg>
  )
}
