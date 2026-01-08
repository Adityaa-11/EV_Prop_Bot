"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Calendar, List, TrendingUp, GitCompare, Activity, Settings, Menu, FileText } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"

const navigationItems = [
  { name: "Games", href: "/games", icon: Calendar },
  { name: "Props", href: "/props", icon: List },
  { name: "+EV Plays", href: "/ev-plays", icon: TrendingUp },
  { name: "Middles", href: "/middles", icon: GitCompare },
  { name: "Line Movement", href: "/line-movement", icon: Activity },
  { name: "Settings", href: "/settings", icon: Settings },
  { name: "Notes", href: "/notes", icon: FileText },
]

const sportsFilters = [
  { name: "NBA", code: "NBA" },
  { name: "NFL", code: "NFL" },
  { name: "NHL", code: "NHL" },
  { name: "MLB", code: "MLB" },
  { name: "NCAAB", code: "NCAAB" },
  { name: "NCAAF", code: "NCAAF" },
]

export function AppSidebar() {
  const pathname = usePathname()
  const [isOpen, setIsOpen] = React.useState(false)

  const SidebarContent = () => (
    <div className="flex h-full flex-col bg-sidebar">
      {/* Logo/Brand */}
      <div className="border-b border-sidebar-border px-6 py-5">
        <Link href="/games" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
            <TrendingUp className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="text-lg font-bold text-sidebar-foreground">EV DASHBOARD</span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 border-b border-sidebar-border px-3 py-4">
        {navigationItems.map((item) => {
          const Icon = item.icon
          const isActive = pathname === item.href
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setIsOpen(false)}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.name}
            </Link>
          )
        })}
      </nav>

      {/* Sports Filters */}
      <div className="px-3 py-4">
        <h3 className="mb-3 px-3 text-xs font-semibold uppercase tracking-wider text-sidebar-foreground/50">Sports</h3>
        <div className="space-y-1">
          {sportsFilters.map((sport) => (
            <button
              key={sport.code}
              className="flex w-full items-center rounded-md px-3 py-2 text-sm text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
            >
              {sport.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  )

  return (
    <>
      {/* Mobile Trigger */}
      <Sheet open={isOpen} onOpenChange={setIsOpen}>
        <SheetTrigger asChild className="lg:hidden">
          <Button variant="ghost" size="icon" className="fixed left-4 top-4 z-40">
            <Menu className="h-5 w-5" />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-64 p-0">
          <SidebarContent />
        </SheetContent>
      </Sheet>

      {/* Desktop Sidebar */}
      <aside className="hidden h-screen w-64 border-r border-sidebar-border lg:block">
        <SidebarContent />
      </aside>
    </>
  )
}
