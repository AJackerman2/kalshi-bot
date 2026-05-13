export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const params = await searchParams;
  const next = params.next ?? "/";
  const error = params.error;
  return (
    <main className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-panel p-6 shadow">
        <h1 className="text-lg font-semibold tracking-tight">Kalshi Maker Bot</h1>
        <p className="mb-6 text-sm text-muted">Enter dashboard password.</p>
        <form action="/api/login" method="post" className="space-y-3">
          <input type="hidden" name="next" value={next} />
          <input
            type="password"
            name="password"
            placeholder="password"
            autoFocus
            className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <button
            type="submit"
            className="w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-bg hover:opacity-90"
          >
            Sign in
          </button>
          {error === "bad_password" ? (
            <p className="text-sm text-loss">Wrong password.</p>
          ) : null}
        </form>
      </div>
    </main>
  );
}
