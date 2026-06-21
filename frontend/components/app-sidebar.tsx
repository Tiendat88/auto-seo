"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FileText,
  PlusCircle,
  Eye,
  History,
  BarChart3,
  GitFork,
  TrendingUp,
  Megaphone,
  Server,
  Send,
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
  SidebarHeader,
} from "@/components/ui/sidebar";
import { ThemeToggle } from "@/components/theme-toggle";

const NAV = [
  {
    label: "Quản lý Bài viết",
    items: [
      { title: "Danh sách", href: "/pipeline", icon: FileText },
      { title: "Khởi tạo nhanh", href: "/pipeline/new", icon: PlusCircle },
      { title: "Chiến dịch", href: "/pipeline/campaign", icon: Megaphone },
    ],
  },
  {
    label: "Xuất bản",
    items: [
      { title: "Đích đăng", href: "/publish/targets", icon: Server },
      { title: "Lịch sử đăng", href: "/publish/history", icon: Send },
    ],
  },
  {
    label: "Giám sát Thương hiệu",
    items: [
      { title: "Phân tích thương hiệu", href: "/brand-monitor", icon: Eye },
      { title: "Lịch sử", href: "/brand-monitor/history", icon: History },
    ],
  },
  {
    label: "Tối ưu hóa AEO",
    items: [
      { title: "Phân tích nội dung", href: "/aeo", icon: BarChart3 },
      { title: "Khai phá truy vấn", href: "/aeo/fanout", icon: GitFork },
    ],
  },
];

export function AppSidebar() {
  const pathname = usePathname();

  // Chỉ item có href khớp dài nhất với pathname mới active — tránh item cha
  // (vd /brand-monitor) sáng cùng item con (vd /brand-monitor/history).
  const activeHref = NAV.flatMap((g) => g.items.map((i) => i.href))
    .filter((href) => pathname === href || pathname.startsWith(href + "/"))
    .sort((a, b) => b.length - a.length)[0];

  return (
    <Sidebar className="border-r border-blue-500/10">
      <SidebarHeader className="border-b border-blue-500/10 px-4 py-4">
        <Link href="/pipeline" className="flex items-center gap-2 font-bold text-blue-600 dark:text-blue-400">
          <TrendingUp className="h-6 w-6 text-blue-600 dark:text-blue-400" />
          <span className="text-xl tracking-tight">AutoSEO</span>
        </Link>
      </SidebarHeader>
      <SidebarContent className="px-2 py-4">
        {NAV.map((group) => (
          <SidebarGroup key={group.label} className="mb-2">
            <SidebarGroupLabel className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/70 mb-2 px-2">
              {group.label}
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  const actuallyActive = item.href === activeHref;

                  return (
                    <SidebarMenuItem key={item.href} className="mb-1">
                      <SidebarMenuButton 
                        render={<Link href={item.href} />} 
                        isActive={actuallyActive}
                        className={`transition-all duration-200 hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-500/10 dark:hover:text-blue-400 ${
                          actuallyActive ? "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300 font-medium" : "text-muted-foreground"
                        }`}
                      >
                        <item.icon className={`h-4 w-4 ${actuallyActive ? "text-blue-600 dark:text-blue-400" : ""}`} />
                        <span>{item.title}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
        <ThemeToggle />
      </SidebarContent>
    </Sidebar>
  );
}
