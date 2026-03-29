"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FileText,
  Plus,
  Eye,
  History,
  BarChart3,
  GitFork,
  LayoutDashboard,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar";
import { ThemeToggle } from "@/components/theme-toggle";

const NAV = [
  {
    label: "Pipeline",
    items: [
      { title: "Jobs", href: "/pipeline", icon: FileText },
      { title: "New Job", href: "/pipeline/new", icon: Plus },
    ],
  },
  {
    label: "Brand Monitor",
    items: [
      { title: "New Analysis", href: "/brand-monitor", icon: Eye },
      { title: "History", href: "/brand-monitor/history", icon: History },
    ],
  },
  {
    label: "AEO",
    items: [
      { title: "Analyze", href: "/aeo", icon: BarChart3 },
      { title: "Fan-out", href: "/aeo/fanout", icon: GitFork },
    ],
  },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar>
      <SidebarHeader className="border-b px-4 py-3">
        <Link href="/pipeline" className="flex items-center gap-2 font-semibold">
          <LayoutDashboard className="h-5 w-5" />
          AutoSEO
        </Link>
      </SidebarHeader>
      <SidebarContent>
        {NAV.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton render={<Link href={item.href} />} isActive={pathname === item.href}>
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter className="border-t p-2">
        <ThemeToggle />
      </SidebarFooter>
    </Sidebar>
  );
}
