"use client"

import { useCallback, useEffect, useState } from "react"
import { Clock, RefreshCw, Zap } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { getLiveDashboard, type LiveResponse } from "@/lib/api"

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
})

function executionBadge(status?: string) {
  switch (status) {
    case "pending":
      return <Badge variant="outline">Pending</Badge>
    case "claimed":
      return <Badge variant="secondary">Claimed</Badge>
    case "submitted":
      return <Badge>Submitted</Badge>
    case "failed":
      return <Badge variant="destructive">Failed</Badge>
    case "skipped":
      return <Badge variant="secondary">Shadow</Badge>
    default:
      return <Badge variant="outline">{status || "unknown"}</Badge>
  }
}

export default function LiveTradingPage() {
  const [data, setData] = useState<LiveResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const response = await getLiveDashboard()
      setData(response)
      setError(null)
    } catch {
      setError(
        `Unable to load live execution state from ${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}`,
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 10_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  if (loading && !data) {
    return <div className="container mx-auto px-4 py-10 text-muted-foreground">Loading live execution…</div>
  }

  const heartbeat = data?.executor_heartbeat

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold">Live Execution</h1>
            <Badge variant={data?.enabled ? "default" : "secondary"}>
              {data?.enabled ? "ENABLED" : "DISABLED"}
            </Badge>
            {data?.shadow_mode && <Badge variant="outline">SHADOW MODE</Badge>}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Hermes + Playwright queue on Mac Mini — Railway remains the EV brain
          </p>
        </div>
        <Button variant="outline" onClick={() => void refresh()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {error && <Card className="mb-6 border-destructive p-4 text-sm text-destructive">{error}</Card>}

      {!data?.enabled && (
        <Card className="mb-6 border-amber-500/50 bg-amber-500/10 p-4">
          <p className="font-semibold text-amber-600 dark:text-amber-400">Live execution disabled</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Set `LIVE_EXECUTION_ENABLED=true` on Railway after shadow validation. Kill switch: set it back to false.
          </p>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-5">
          <p className="text-sm text-muted-foreground">Live stake</p>
          <p className="mt-2 text-2xl font-bold">{currency.format(data?.stake ?? 5)}</p>
          <p className="mt-1 text-xs text-muted-foreground">Per approved slip</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-muted-foreground">Pending queue</p>
          <p className="mt-2 text-2xl font-bold">{data?.pending_execution ?? 0}</p>
          <p className="mt-1 text-xs text-muted-foreground">Awaiting Hermes claim</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-muted-foreground">Open live slips</p>
          <p className="mt-2 text-2xl font-bold">{data?.open_live_entries ?? 0}</p>
          <p className="mt-1 text-xs text-muted-foreground">Real-money exposure</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-muted-foreground">Hermes heartbeat</p>
          <p className="mt-2 text-lg font-bold">
            {heartbeat?.checked_at ? new Date(heartbeat.checked_at).toLocaleString() : "No ping yet"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {heartbeat?.worker_id || "hermes-mac-mini"} · {heartbeat?.last_action || "idle"}
          </p>
        </Card>
      </div>

      <div className="mb-4 mt-8 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Live ledger</h2>
        <span className="text-xs text-muted-foreground">Updates every 10 seconds</span>
      </div>

      {!data?.entries.length ? (
        <Card className="p-12 text-center">
          <Zap className="mx-auto h-12 w-12 text-muted-foreground" />
          <h3 className="mt-4 text-lg font-semibold">No live entries yet</h3>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
            Live slips appear when `EXECUTION_MODE=live`, execution is enabled, and an excellent candidate clears risk.
          </p>
        </Card>
      ) : (
        <div className="space-y-4">
          {data.entries.map((entry) => (
            <Card key={entry.id} className="overflow-hidden">
              <div className="flex flex-col justify-between gap-3 border-b p-5 sm:flex-row sm:items-center">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>{entry.platform === "prizepicks" ? "PrizePicks" : "Underdog"}</Badge>
                  <Badge variant="outline">{entry.sport}</Badge>
                  <Badge variant="destructive">LIVE</Badge>
                  {executionBadge(entry.execution_status)}
                </div>
                <div className="text-sm sm:text-right">
                  <p className="font-semibold">
                    {currency.format(entry.stake)} to return {currency.format(entry.potential_payout)}
                  </p>
                  {entry.external_ticket_id && (
                    <p className="text-muted-foreground">Ticket {entry.external_ticket_id}</p>
                  )}
                </div>
              </div>

              {entry.execution_error && (
                <div className="border-b bg-destructive/5 px-5 py-3 text-sm text-destructive">
                  {entry.execution_error}
                </div>
              )}

              <div className="grid gap-4 p-5 lg:grid-cols-2">
                {entry.legs.map((leg) => (
                  <div key={leg.candidate_id} className="rounded-lg border p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold">{leg.player_name}</p>
                        <p className="text-sm text-muted-foreground">{leg.stat_type}</p>
                      </div>
                      <Badge variant={leg.side === "OVER" ? "default" : "secondary"}>
                        {leg.side} {leg.line}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-col justify-between gap-2 bg-muted/30 px-5 py-3 text-xs text-muted-foreground sm:flex-row">
                <span>{entry.status === "settled" ? `${entry.result}` : "Open slip"}</span>
                <span className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  Locks {entry.lock_time ? new Date(entry.lock_time).toLocaleString() : "unknown"}
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
