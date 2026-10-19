import { useEffect, useState, type ReactNode } from "react";
import { Navigate, Route, Routes, useParams, useSearchParams } from "react-router-dom";
import { api } from "./api/client";
import { useAuth } from "./auth/AuthProvider";
import { SettingsPage } from "./components/SettingsPage";
import { Editor } from "./components/Editor";
import { LoginPage } from "./components/LoginPage";
import { SourcesPage } from "./components/SourcesPage";
import { UsersPage } from "./components/UsersPage";
import { CleanupPage } from "./components/cleanup/CleanupPage";
import type { EditorSession } from "./types";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return <p className="p-8 text-app-text-muted">Loading…</p>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function EditorRoute() {
  const { sourceId } = useParams();
  const [searchParams] = useSearchParams();
  const segmentParam = searchParams.get("segment");
  const initialSegmentId = segmentParam ? Number(segmentParam) : null;
  const [session, setSession] = useState<EditorSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sourceId) return;
    api
      .getSession(Number(sourceId))
      .then(setSession)
      .catch((e) => setError(String(e)));
  }, [sourceId]);

  if (error) return <p className="p-8 text-red-600 dark:text-red-400">{error}</p>;
  if (!session) return <p className="p-8 text-app-text-muted">Loading…</p>;
  return (
    <Editor
      session={session}
      initialSegmentId={
        initialSegmentId && !Number.isNaN(initialSegmentId)
          ? initialSegmentId
          : undefined
      }
    />
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <SourcesPage />
          </RequireAuth>
        }
      />
      <Route
        path="/editor/:sourceId"
        element={
          <RequireAuth>
            <EditorRoute />
          </RequireAuth>
        }
      />
      <Route
        path="/settings"
        element={
          <RequireAuth>
            <SettingsPage />
          </RequireAuth>
        }
      />
      <Route
        path="/users"
        element={
          <RequireAuth>
            <UsersPage />
          </RequireAuth>
        }
      />
      <Route
        path="/cleanup"
        element={
          <RequireAuth>
            <CleanupPage />
          </RequireAuth>
        }
      />
    </Routes>
  );
}
