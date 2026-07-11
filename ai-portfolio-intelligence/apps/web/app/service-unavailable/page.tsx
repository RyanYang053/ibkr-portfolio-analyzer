export default function ServiceUnavailablePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6 py-12">
      <h1 className="text-2xl font-semibold text-slate-900">Service temporarily unavailable</h1>
      <p className="mt-3 text-slate-600">
        The portfolio platform could not reach the authentication or analytics backend. Try again in a few minutes.
      </p>
    </main>
  );
}
