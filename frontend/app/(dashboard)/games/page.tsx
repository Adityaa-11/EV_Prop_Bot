"use client"

import { useEffect, useState } from "react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { RefreshCw, Loader2, AlertCircle, Calendar } from "lucide-react"
import { getGames, type GamesResponse } from "@/lib/api"

export default function GamesPage() {
  const [data, setData] = useState<GamesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sport, setSport] = useState("nba")

  const currentDate = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  })

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getGames(sport)
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch data")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [sport])

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6">
      {/* Page Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold">Today&apos;s Games</h1>
          <p className="mt-1 text-sm text-muted-foreground">{currentDate}</p>
        </div>
        <Button onClick={fetchData} disabled={loading} variant="outline" size="sm">
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap gap-3">
        <Select value={sport} onValueChange={setSport}>
          <SelectTrigger className="w-32">
            <SelectValue placeholder="Sport" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="nba">NBA</SelectItem>
            <SelectItem value="nfl">NFL</SelectItem>
            <SelectItem value="mlb">MLB</SelectItem>
            <SelectItem value="nhl">NHL</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Error State */}
      {error && (
        <Card className="border-destructive bg-destructive/10 p-6">
          <div className="flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <div>
              <p className="font-medium text-destructive">Error loading data</p>
              <p className="text-sm text-muted-foreground">{error}</p>
              <p className="mt-2 text-xs text-muted-foreground">
                Make sure the API server is running at {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}
              </p>
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

      {/* Content */}
      {!loading && !error && data && (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="p-4">
              <div className="text-sm text-muted-foreground">Sport</div>
              <div className="mt-1 text-2xl font-bold">{data.sport}</div>
            </Card>
            <Card className="p-4">
              <div className="text-sm text-muted-foreground">Total Props</div>
              <div className="mt-1 text-2xl font-bold">{data.total_props}</div>
            </Card>
            <Card className="p-4">
              <div className="text-sm text-muted-foreground">PrizePicks</div>
              <div className="mt-1 text-2xl font-bold">{data.platforms.prizepicks}</div>
            </Card>
            <Card className="p-4">
              <div className="text-sm text-muted-foreground">Underdog</div>
              <div className="mt-1 text-2xl font-bold">{data.platforms.underdog}</div>
            </Card>
          </div>

          {/* Teams with Props */}
          {data.teams_with_props.length > 0 ? (
            <Card className="p-6">
              <h2 className="mb-4 text-lg font-semibold">Teams with Props Available</h2>
              <div className="flex flex-wrap gap-2">
                {data.teams_with_props.map((team) => (
                  <Badge key={team} variant="secondary" className="text-sm">
                    {team}
                  </Badge>
                ))}
              </div>
            </Card>
          ) : (
            <Card className="p-12 text-center">
              <Calendar className="mx-auto h-12 w-12 text-muted-foreground" />
              <p className="mt-4 text-lg font-medium">No games found</p>
              <p className="mt-2 text-sm text-muted-foreground">
                No {sport.toUpperCase()} props available right now. Check back closer to game time.
              </p>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
