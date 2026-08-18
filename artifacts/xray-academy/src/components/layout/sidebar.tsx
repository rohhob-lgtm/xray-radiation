import { Link, useLocation } from "wouter";
import {
  Settings, Languages, Database, BarChart2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useListProviders } from "@workspace/api-client-react";

export function Sidebar() {
  const [location] = useLocation();
  const { data: providers } = useListProviders();
  const activeProvider = providers?.find((p) => p.is_active);

  // Translation Studio clone — navigation is scoped to the translation feature.
  const sections = [
    {
      label: "Translation",
      links: [
        { href: "/translation", label: "Translation Studio", icon: Languages },
        { href: "/translation-dictionary", label: "Glossary & Memory", icon: Database },
        { href: "/translation/cost", label: "Cost & Usage", icon: BarChart2 },
      ],
    },
  ];

  return (
    <div className="flex h-screen w-64 flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border shadow-xl z-10">
      <div className="flex items-center gap-3 p-6 border-b border-sidebar-border shrink-0">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground shadow-md">
          <ShieldAlert className="h-6 w-6" />
        </div>
        <div>
          <h1 className="text-lg font-bold tracking-tight">Translation Studio</h1>
          <p className="text-xs text-sidebar-foreground/70 uppercase tracking-widest font-mono">Technical · Engineering</p>
        </div>
      </div>

      <div className="flex-1 overflow-auto py-4">
        <nav className="flex flex-col gap-4 px-4">
          {sections.map((section) => (
            <div key={section.label}>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40 mb-1.5 px-2">
                {section.label}
              </div>
              <div className="flex flex-col gap-0.5">
                {section.links.map((link) => {
                  const isActive = location === link.href || location.startsWith(link.href + '/');
                  return (
                    <Link
                      key={link.href}
                      href={link.href}
                      className={cn(
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all duration-200",
                        isActive
                          ? "bg-sidebar-primary text-sidebar-primary-foreground shadow-sm"
                          : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                      )}
                    >
                      <link.icon className="h-4 w-4 shrink-0" />
                      <span className="truncate">{link.label}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </div>

      <div className="p-4 border-t border-sidebar-border shrink-0">
        <Link
          href="/settings"
          className={cn(
            "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors w-full",
            location === "/settings"
              ? "bg-sidebar-primary text-sidebar-primary-foreground"
              : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          )}
        >
          <Settings className="h-4 w-4" />
          Settings
        </Link>
        <div className="mt-3 px-3 flex items-center justify-between text-xs text-sidebar-foreground/50">
          <span className="flex items-center gap-1.5">
            <div className={cn("h-2 w-2 rounded-full", activeProvider ? "bg-green-500" : "bg-red-500")} />
            AI Status
          </span>
          <span className="font-mono">{activeProvider?.name || "Disconnected"}</span>
        </div>
      </div>
    </div>
  );
}
