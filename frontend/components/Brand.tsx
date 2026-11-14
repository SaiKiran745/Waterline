import Link from "next/link";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className={`brand ${compact ? "compact" : ""}`}>
      <span className="brand-mark"><i /><i /><i /></span>
      <span><b>WATERLINE</b>{compact ? null : <small>INTERIOR FLOOD INTELLIGENCE</small>}</span>
    </Link>
  );
}
