import {
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
} from "@heroicons/react/20/solid";
import type { ComponentType, SVGProps } from "react";
import type { SystemAlert } from "../types";

const SEVERITY_CLASS: Record<SystemAlert["severity"], string> = {
  error: "app-alert-error",
  warning: "app-alert-warning",
  info: "app-alert-info",
};

const SEVERITY_LABEL: Record<SystemAlert["severity"], string> = {
  error: "Error",
  warning: "Warning",
  info: "Info",
};

const SEVERITY_ICON: Record<
  SystemAlert["severity"],
  ComponentType<SVGProps<SVGSVGElement>>
> = {
  error: ExclamationCircleIcon,
  warning: ExclamationTriangleIcon,
  info: InformationCircleIcon,
};

export function SystemAlerts({
  alerts,
  className = "",
  compact = false,
}: {
  alerts: SystemAlert[];
  className?: string;
  compact?: boolean;
}) {
  if (!alerts.length) return null;

  return (
    <div className={`space-y-2 ${className}`}>
      {alerts.map((alert) => {
        const Icon = SEVERITY_ICON[alert.severity] ?? ExclamationTriangleIcon;
        return (
          <div
            key={alert.id}
            className={`flex gap-2 ${SEVERITY_CLASS[alert.severity] ?? "app-alert-warning"}`}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0 opacity-80" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className={compact ? "text-xs" : "text-sm"}>
                <strong>{SEVERITY_LABEL[alert.severity]}:</strong> {alert.message}
              </p>
              {alert.hint && (
                <p className={`mt-1 text-app-text-muted ${compact ? "text-xs" : "text-sm"}`}>
                  {alert.hint}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
