import { FormEvent, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { ThemeToggle } from "./ThemeToggle";

export function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">MoTranscript</h1>
          <p className="text-sm text-app-text-muted">Sign in to continue</p>
        </div>
        <ThemeToggle />
      </div>
      <form onSubmit={(e) => void onSubmit(e)} className="app-card space-y-4 p-6">
        <label className="block text-sm">
          <span className="mb-1 block text-app-text-muted">Email</span>
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="app-input w-full"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-app-text-muted">Password</span>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="app-input w-full"
          />
        </label>
        {error && <p className="app-alert-error text-sm">{error}</p>}
        <button type="submit" disabled={busy} className="app-btn-primary w-full">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
