"use client"

import { useEffect, useState } from "react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ArrowUp, ArrowDown, RefreshCw, Loader2, AlertCircle } from "lucide-react"
import { getEVPlays, type EVPlay, type EVResponse } from "@/lib/api"

export default function EVPlaysPage() {
  const [data, setData] = useState<EVResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sport, setSport] = useState("all")
  const [platform, setPlatform] = useState<string | undefined>(undefined)

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getEVPlays({ sport, platform })
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch data")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [sport, platform])

  const formatOdds = (odds: number) => (odds > 0 ? `+${odds}` : odds.toString())

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6">
      {/* Page Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-primary">+EV Plays</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {loading ? "Loading..." : `${data?.count || 0} plays found`}
          </p>
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
            <SelectItem value="all">All Sports</SelectItem>
            <SelectItem value="nba">NBA</SelectItem>
            <SelectItem value="nfl">NFL</SelectItem>
            <SelectItem value="mlb">MLB</SelectItem>
            <SelectItem value="nhl">NHL</SelectItem>
          </SelectContent>
        </Select>

        <Select value={platform || "all"} onValueChange={(v) => setPlatform(v === "all" ? undefined : v)}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Platform" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Platforms</SelectItem>
            <SelectItem value="prizepicks">PrizePicks</SelectItem>
            <SelectItem value="underdog">Underdog</SelectItem>
            <SelectItem value="betr">Betr</SelectItem>
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

      {/* Empty State */}
      {!loading && !error && data?.count === 0 && (
        <Card className="p-12 text-center">
          <p className="text-lg font-medium">No +EV plays found</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Try a different sport or check back when games are scheduled
          </p>
        </Card>
      )}

      {/* EV Play Cards */}
      {!loading && !error && data && data.plays.length > 0 && (
        <div className="space-y-4">
          {data.sharp_books_used.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Sharp odds from: {data.sharp_books_used.join(", ")}
            </p>
          )}
          {data.plays.map((play, idx) => (
            <EVPlayAPICard key={`${play.prop.id}-${idx}`} play={play} />
          ))}
        </div>
      )}
    </div>
  )
}

function EVPlayAPICard({ play }: { play: EVPlay }) {
  const { prop, sharp_odds, recommended_play, win_probability, ev_percentage, best_for } = play

  const evColor =
    ev_percentage >= 5 ? "border-green-500" : ev_percentage >= 2 ? "border-yellow-500" : "border-orange-500"

  const formatOdds = (odds: number) => (odds > 0 ? `+${odds}` : odds.toString())

  return (
    <Card className={`border-l-4 ${evColor} p-6`}>
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        {/* Left: EV Badge and Player Info */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="font-mono text-lg font-bold">
              +{ev_percentage.toFixed(1)}% EV
            </Badge>
            <Badge variant="secondary" className="capitalize">
              {prop.platform}
            </Badge>
          </div>

          <div>
            <h3 className="text-xl font-bold">{prop.player_name}</h3>
            <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
              <span>{prop.team}</span>
              <span>•</span>
              <span>{prop.sport}</span>
              {prop.game_time && (
                <>
                  <span>•</span>
                  <span>{new Date(prop.game_time).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}</span>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {recommended_play === "OVER" ? (
              <ArrowUp className="h-5 w-5 text-green-500" />
            ) : (
              <ArrowDown className="h-5 w-5 text-red-500" />
            )}
            <span className="font-semibold">
              {recommended_play} {prop.line} {prop.stat_type}
            </span>
          </div>
        </div>

        {/* Right: Stats and Best For */}
        <div className="space-y-3 md:text-right">
          <div className="flex flex-wrap gap-4 text-sm md:justify-end">
            <span className="font-numeric">
              <span className="text-muted-foreground">Win%:</span>{" "}
              <span className="font-bold">{win_probability.toFixed(1)}%</span>
            </span>
            {sharp_odds && (
              <span className="font-numeric text-muted-foreground">
                Book: {sharp_odds.bookmaker} {formatOdds(sharp_odds.over_odds)}/{formatOdds(sharp_odds.under_odds)}
              </span>
            )}
          </div>

          {best_for.length > 0 && (
            <div className="flex flex-wrap gap-2 md:justify-end">
              {best_for.map((slip) => (
                <Badge key={slip} variant="outline" className="text-xs">
                  ✓ {slip.replace("_", "-")}
                </Badge>
              ))}
            </div>
          )}

          {sharp_odds?.is_sharp && (
            <Badge variant="default" className="bg-blue-600">
              Sharp Line
            </Badge>
          )}
        </div>
      </div>
    </Card>
  )
}
