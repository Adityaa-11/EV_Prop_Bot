"use client"

import * as React from "react"
import { Search, RefreshCw, Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function AppHeader() {
  const { theme, setTheme } = useTheme()
  const [lastUpdated, setLastUpdated] = React.useState<Date>(new Date())

  const handleRefresh = () => {
    setLastUpdated(new Date())
    // In a real app, this would trigger data refetch
  }

  const formatLastUpdated = (date: Date) => {
    const minutes = Math.floor((new Date().getTime() - date.getTime()) / 60000)
    if (minutes === 0) return "Just now"
    if (minutes === 1) return "1 min ago"
    return `${minutes} min ago`
  }

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-16 items-center gap-4 px-6">
        <div className="flex flex-1 items-center gap-4">
          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input type="search" placeholder="Search player..." className="pl-9" />
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Last Updated */}
          <span className="hidden text-sm text-muted-foreground sm:inline">
            Last updated: {formatLastUpdated(lastUpdated)}
          </span>

          {/* Refresh Button */}
          <Button variant="ghost" size="icon" onClick={handleRefresh} title="Refresh data">
            <RefreshCw className="h-4 w-4" />
          </Button>

          {/* Theme Toggle */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            title="Toggle theme"
          >
            <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          </Button>
        </div>
      </div>
    </header>
  )
}
