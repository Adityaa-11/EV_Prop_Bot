"use client"

import { useCallback, useEffect, useState } from "react"
import { Activity, RefreshCw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { getLineHistory, type LineObservation } from "@/lib/api"

export default function LineMovementPage() {
  const [observations, setObservations] = useState<LineObservation[]>([])
  const [sport, setSport] = useState("mlb")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const response = await getLineHistory({ sport, limit: 100 })
      setObservations(response.observations)
      setError(null)
    } catch {
      setError("Unable to load line history")
    } finally {
      setLoading(false)
    }
  }, [sport])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 15_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-3xl font-bold">Line Movement</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Persisted candidate observations from paper scans
          </p>
        </div>
        <div className="flex items-center gap-2">
          {["mlb", "nba", "nfl", "nhl"].map((code) => (
            <Button
              key={code}
              size="sm"
              variant={sport === code ? "default" : "outline"}
              onClick={() => setSport(code)}
            >
              {code.toUpperCase()}
            </Button>
          ))}
          <Button variant="outline" onClick={() => void refresh()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {error && <Card className="mb-6 border-destructive p-4 text-sm text-destructive">{error}</Card>}

      {loading && !observations.length ? (
        <Card className="p-12 text-center text-muted-foreground">Loading observations…</Card>
      ) : !observations.length ? (
        <Card className="p-12 text-center">
          <Activity className="mx-auto h-12 w-12 text-muted-foreground" />
          <h2 className="mt-4 text-lg font-semibold">No observations yet</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Line history appears after a paper scan records candidates for this sport.
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {observations.map((item) => (
            <Card key={`${item.candidate_id}-${item.observed_at}`} className="p-4">
              <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold">{item.player_name}</p>
                    <Badge variant="outline">{item.platform}</Badge>
                    <Badge variant="secondary">{item.side} {item.line}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {item.market_key} · {item.win_probability.toFixed(1)}% · {item.book_count} books
                  </p>
                </div>
                <div className="text-xs text-muted-foreground sm:text-right">
                  <p>{item.sport}</p>
                  <p>{new Date(item.observed_at).toLocaleString()}</p>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
