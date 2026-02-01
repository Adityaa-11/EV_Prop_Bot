"use client"

import { useEffect, useState, useRef } from "react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ArrowUp, ArrowDown, RefreshCw, Loader2, AlertCircle, Database } from "lucide-react"
import { getEVPlays, type EVPlay, type EVResponse, type BookOdds } from "@/lib/api"

export default function EVPlaysPage() {
  const [data, setData] = useState<(EVResponse & { cached?: boolean; cache_fresh?: boolean }) | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sport, setSport] = useState("all")
  const [platform, setPlatform] = useState<string | undefined>(undefined)
  const initialFetch = useRef(false)

  const fetchData = async (forceRefresh = false) => {
    setLoading(true)
    setError(null)
    try {
      const result = await getEVPlays({ sport, platform, refresh: forceRefresh })
      setData(result as EVResponse & { cached?: boolean; cache_fresh?: boolean })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch data")
    } finally {
      setLoading(false)
    }
  }

  // Only fetch from cache on initial load (no API cost)
  useEffect(() => {
    if (!initialFetch.current) {
      initialFetch.current = true
      fetchData(false) // Load from cache
    }
  }, [])

  // When filters change, fetch from cache (not fresh)
  useEffect(() => {
    if (initialFetch.current) {
      fetchData(false)
    }
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

// Book name to display abbreviation
const BOOK_DISPLAY: Record<string, { abbr: string; color: string }> = {
  pinnacle: { abbr: "PIN", color: "bg-purple-600" },
  draftkings: { abbr: "DK", color: "bg-green-600" },
  fanduel: { abbr: "FD", color: "bg-blue-600" },
  betmgm: { abbr: "MGM", color: "bg-yellow-600" },
  bovada: { abbr: "BOV", color: "bg-red-600" },
  betonlineag: { abbr: "BOL", color: "bg-orange-600" },
  caesars: { abbr: "CZR", color: "bg-teal-600" },
  betrivers: { abbr: "BR", color: "bg-indigo-600" },
  lowvig: { abbr: "LV", color: "bg-gray-600" },
  mybookieag: { abbr: "MB", color: "bg-pink-600" },
}

function EVPlayAPICard({ play }: { play: EVPlay }) {
  const { prop, sharp_odds, all_book_odds, recommended_play, win_probability, ev_percentage, best_for } = play

  const evColor =
    ev_percentage >= 5 ? "border-green-500" : ev_percentage >= 2 ? "border-yellow-500" : "border-orange-500"

  const formatOdds = (odds: number) => (odds > 0 ? `+${odds}` : odds.toString())
  
  // Get display info for a book
  const getBookDisplay = (bookmaker: string) => {
    return BOOK_DISPLAY[bookmaker] || { abbr: bookmaker.slice(0, 3).toUpperCase(), color: "bg-gray-500" }
  }

  return (
    <Card className={`border-l-4 ${evColor} p-6`}>
      <div className="flex flex-col gap-4">
        {/* Top Row: EV Badge, Player Info, Stats */}
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
              <span className="font-numeric">
                <span className="text-muted-foreground">Fair Odds:</span>{" "}
                <span className="font-bold">{Math.round(-100 * win_probability / (100 - win_probability))}</span>
              </span>
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

        {/* Book Odds Comparison Table */}
        {all_book_odds && all_book_odds.length > 0 && (
          <div className="mt-2 border-t pt-4">
            <p className="mb-2 text-xs font-medium text-muted-foreground">Sportsbook Comparison</p>
            <div className="flex flex-wrap gap-3">
              {all_book_odds.slice(0, 6).map((book, idx) => {
                const display = getBookDisplay(book.bookmaker)
                const isSharp = book.bookmaker === sharp_odds?.bookmaker
                return (
                  <div
                    key={`${book.bookmaker}-${idx}`}
                    className={`flex flex-col items-center rounded-lg border p-2 text-center ${
                      isSharp ? "border-primary bg-primary/5" : "border-border"
                    }`}
                  >
                    <Badge className={`${display.color} mb-1 text-xs text-white`}>
                      {display.abbr}
                    </Badge>
                    <span className="text-sm font-bold">{book.line}</span>
                    <span className="text-xs text-green-600">{formatOdds(book.over_odds)}</span>
                    <span className="text-xs text-red-600">{formatOdds(book.under_odds)}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}
