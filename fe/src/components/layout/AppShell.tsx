import { Link } from "react-router-dom";

type AppShellProps = {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
};

export function AppShell({
  children,
  title = "UI TestGen",
  subtitle = "Research pipeline — screenshots to behaviour scenarios",
}: AppShellProps) {
  return (
    <div className="app-shell-bg min-h-screen text-[var(--fg-primary)]">
      <div className="container mx-auto p-4 sm:p-6 lg:p-8">
        <header className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-gradient text-4xl font-extrabold tracking-tight sm:text-5xl">
              {title}
            </h1>
            {subtitle ? (
              <p className="mt-2 max-w-xl text-sm text-[var(--fg-muted)]">
                {subtitle}
              </p>
            ) : null}
          </div>
          <nav className="flex flex-wrap gap-4 text-sm font-semibold">
            <Link
              className="text-[var(--accent)] transition hover:brightness-125"
              to="/"
            >
              Runs
            </Link>
            <Link
              className="text-[var(--accent)] transition hover:brightness-125"
              to="/admin"
            >
              Admin
            </Link>
          </nav>
        </header>
        {children}
      </div>
    </div>
  );
}
