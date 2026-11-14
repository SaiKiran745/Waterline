import Link from "next/link";

export default function NotFound() {
  return (
    <main className="center-state">
      <div className="state-card">
        <span className="eyebrow">No building found</span>
        <h1>This dossier is not in the current data source.</h1>
        <Link className="primary-button" href="/">Return to triage</Link>
      </div>
    </main>
  );
}
