"use client";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="center-state">
      <div className="state-card error-card">
        <h1>Waterline could not load.</h1>
        <p>{error.message || "The data source returned an unexpected response."}</p>
        <button className="primary-button" onClick={reset}>Try again</button>
      </div>
    </main>
  );
}
