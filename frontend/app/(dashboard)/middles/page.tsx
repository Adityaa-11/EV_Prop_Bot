"use client"

import { useEffect, useState, useRef } from "react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { RefreshCw, Loader2, AlertCircle, ArrowUp, ArrowDown, GitCompare, Database } from "lucide-react"
import { getMiddles, type MiddlesResponse, type Middle } from "@/lib/api"

export default function MiddlesPage() {
  const [data, setData] = useState<(MiddlesResponse & { cached?: boolean; cache_fresh?: boolean }) | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sport, setSport] = useState("all")
  const initialFetch = useRef(false)

  const fetchData = async (forceRefresh = false) => {
    setLoading(true)
    setError(null)
    try {
      const result = await getMiddles({ sport, refresh: forceRefresh })
      setData(result as MiddlesResponse & { cached?: boolean; cache_fresh?: boolean })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch data")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!initialFetch.current) {
      initialFetch.current = true
      fetchData(false)
    }
  }, [])

  useEffect(() => {
    if (initialFetch.current) {
      fetchData(false)
    }
  }, [sport])

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6">
      {/* Page Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold">Middles & Arbitrage</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {loading ? "Loading..." : `${data?.count || 0} opportunities`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data?.cached && (
            <Badge variant="secondary" className="gap-1 text-xs">
              <Database className="h-3 w-3" />
              {data.cache_fresh ? "Cached" : "Stale"}
            </Badge>
          )}
          <Button onClick={() => fetchData(true)} disabled={loading} variant="outline" size="sm">
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap gap-3">
        <Select value={sport} onValueChange={setSport}>
          <SelectTrigger className="w-32">
            <SelectValue placeholder="Sport" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sports</SelectItem>
            <SelectItem value="nba">NBA</SelectItem>
            <SelectItem value="nfl">NFL</SelectItem>
            <SelectItem value="mlb">MLB</SelectItem>
            <SelectItem value="nhl">NHL</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Info Banner */}
      <Card className="mb-6 border-blue-500/50 bg-blue-500/10 p-4">
        <div className="flex items-start gap-3">
          <GitCompare className="mt-0.5 h-5 w-5 text-blue-500" />
          <div className="text-sm">
            <p className="font-medium">What are Middles?</p>
            <p className="text-muted-foreground">
              A middle opportunity exists when two platforms have different lines for the same prop.
              You can bet UNDER on the higher line and OVER on the lower line - if the result lands
              in between, you win both bets!
            </p>
          </div>
        </div>
      </Card>

      {/* Error State */}
      {error && (
        <Card className="border-destructive bg-destructive/10 p-6">
          <div className="flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <div>
              <p className="font-medium text-destructive">Error loading data</p>
              <p className="text-sm text-muted-foreground">{error}</p>
            </div>
          </div>
        </Card>
      )}

      {/* Loading State */}
      {loading && !error && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && data?.count === 0 && (
        <Card className="p-12 text-center">
          <GitCompare className="mx-auto h-12 w-12 text-muted-foreground" />
          <p className="mt-4 text-lg font-medium">No middle opportunities found</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Middles appear when platforms have different lines for the same prop
          </p>
        </Card>
      )}

      {/* Middle Cards */}
      {!loading && !error && data && data.middles.length > 0 && (
        <div className="space-y-4">
          {data.middles.map((middle, idx) => (
            <MiddleCard key={`${middle.player_name}-${middle.stat_type}-${idx}`} middle={middle} />
          ))}
        </div>
      )}
    </div>
  )
}

function MiddleCard({ middle }: { middle: Middle }) {
  return (
    <Card className="border-l-4 border-purple-500 p-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        {/* Left: Player Info */}
        <div className="space-y-2">
          <h3 className="text-xl font-bold">{middle.player_name}</h3>
          <div className="text-sm text-muted-foreground">
            {middle.stat_type} • {middle.sport}
          </div>
          <Badge variant="outline" className="font-mono">
            Spread: {middle.spread.toFixed(1)} pts
          </Badge>
        </div>

        {/* Right: Platforms */}
        <div className="flex gap-4">
          {/* Platform A (Higher Line) */}
          <Card className="min-w-[140px] p-4">
            <div className="text-xs text-muted-foreground uppercase">{middle.platform_a.name}</div>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-2xl font-bold">{middle.platform_a.line}</span>
              <ArrowDown className="h-5 w-5 text-red-500" />
            </div>
            <Badge variant="destructive" className="mt-2">
              UNDER
            </Badge>
          </Card>

          {/* Middle Zone */}
          <div className="flex flex-col items-center justify-center">
            <div className="text-xs text-muted-foreground">Middle</div>
            <div className="font-mono text-lg font-bold text-purple-500">
              {middle.middle_zone.join(", ")}
            </div>
          </div>

          {/* Platform B (Lower Line) */}
          <Card className="min-w-[140px] p-4">
            <div className="text-xs text-muted-foreground uppercase">{middle.platform_b.name}</div>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-2xl font-bold">{middle.platform_b.line}</span>
              <ArrowUp className="h-5 w-5 text-green-500" />
            </div>
            <Badge variant="default" className="mt-2 bg-green-600">
              OVER
            </Badge>
          </Card>
        </div>
      </div>
    </Card>
  )
}
