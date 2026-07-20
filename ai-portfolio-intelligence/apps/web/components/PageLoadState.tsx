export function PageLoading({ label = "Loading…" }: { label?: string }) {
  return <main className="p-8 text-sm text-zinc-600">{label}</main>;
}

export function PageErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-warning bg-amber-50 p-4 text-sm text-warning">
      {message}
    </div>
  );
}
