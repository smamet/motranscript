import { MoonIcon, SunIcon } from "@heroicons/react/20/solid";
import { useTheme } from "../theme/ThemeProvider";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const toDark = theme === "light";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`app-btn-secondary ${className}`}
      title={toDark ? "Switch to dark mode" : "Switch to light mode"}
      aria-label={toDark ? "Switch to dark mode" : "Switch to light mode"}
    >
      {toDark ? (
        <MoonIcon className="h-4 w-4 text-amber-500" aria-hidden />
      ) : (
        <SunIcon className="h-4 w-4 text-amber-400" aria-hidden />
      )}
      <span className="text-xs">{toDark ? "Dark" : "Light"}</span>
    </button>
  );
}
