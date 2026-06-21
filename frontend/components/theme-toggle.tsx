"use client";

import * as React from "react";
import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme } from "next-themes";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

const MODES = [
  { value: "light", label: "Sáng", icon: Sun },
  { value: "dark", label: "Tối", icon: Moon },
  { value: "system", label: "Thiết bị", icon: Monitor },
] as const;

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  // next-themes only knows the active theme after mount; avoid hydration mismatch.
  React.useEffect(() => setMounted(true), []);

  return (
    <SidebarGroup className="mb-2">
      <SidebarGroupLabel className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/70 mb-2 px-2">
        Cài đặt
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {MODES.map(({ value, label, icon: Icon }) => {
            const active = mounted && theme === value;
            return (
              <SidebarMenuItem key={value} className="mb-1">
                <SidebarMenuButton
                  onClick={() => setTheme(value)}
                  isActive={active}
                  className={`transition-all duration-200 hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-500/10 dark:hover:text-blue-400 ${
                    active
                      ? "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300 font-medium"
                      : "text-muted-foreground"
                  }`}
                >
                  <Icon className={`h-4 w-4 ${active ? "text-blue-600 dark:text-blue-400" : ""}`} />
                  <span>{label}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}
