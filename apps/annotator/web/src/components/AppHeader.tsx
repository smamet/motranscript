import type { ComponentType, SVGProps } from "react";
import { NavLink } from "react-router-dom";
import {
  ArrowRightStartOnRectangleIcon,
  Cog6ToothIcon,
  QueueListIcon,
  SparklesIcon,
  UsersIcon,
} from "@heroicons/react/20/solid";
import { useAuth } from "../auth/AuthProvider";
import { Pill } from "./ui";
import { ThemeToggle } from "./ThemeToggle";

type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  adminOnly?: boolean;
};

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Sources", icon: QueueListIcon },
  { to: "/cleanup", label: "Cleanup", icon: SparklesIcon, adminOnly: true },
  { to: "/settings", label: "Settings", icon: Cog6ToothIcon, adminOnly: true },
  { to: "/users", label: "Users", icon: UsersIcon, adminOnly: true },
];

export function AppHeader() {
  const { user, isAdmin, logout } = useAuth();
  const items = NAV_ITEMS.filter((n) => isAdmin || !n.adminOnly);

  return (
    <header className="mb-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">MoTranscript</h1>
          <p className="text-sm text-app-text-muted">Kreol · French · English annotation</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden items-center gap-1.5 text-xs text-app-text-subtle sm:inline-flex">
            {user?.email}
            {isAdmin && <Pill tone="indigo">admin</Pill>}
          </span>
          <button type="button" onClick={() => void logout()} className="app-btn-secondary">
            <ArrowRightStartOnRectangleIcon className="h-4 w-4" aria-hidden />
            Log out
          </button>
          <ThemeToggle />
        </div>
      </div>
      {items.length > 1 && (
        <nav className="flex gap-1 border-b border-app-border" aria-label="Main">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end
              className={({ isActive }) =>
                `-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? "border-indigo-600 text-indigo-700 dark:text-indigo-300"
                    : "border-transparent text-app-text-muted hover:text-app-text"
                }`
              }
            >
              <n.icon className="h-4 w-4" aria-hidden />
              {n.label}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
}
