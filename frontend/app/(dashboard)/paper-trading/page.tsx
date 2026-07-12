"use client"

import { useCallback, useEffect, useState } from "react"
import { Activity, Clock, RefreshCw, Trophy, WalletCards } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { getPaperDashboard, type PaperResponse } from "@/lib/api"

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
})

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail: string
}) {
  return (
    <Card className="p-5">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-bold">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
    </Card>
  )
}

export default function PaperTradingPage() {
  const [data, setData] = useState<PaperResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const response = await getPaperDashboard()
      setData(response)
      setError(null)
    } catch {
      setError("Unable to load the paper portfolio")
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
    return <div className="container mx-auto px-4 py-10 text-muted-foreground">Loading paper portfolio…</div>
  }

  const summary = data?.summary
  const scheduler = data?.scheduler
  const quota = data?.quota

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold">Paper Trading</h1>
            <Badge variant="secondary">SIMULATION ONLY</Badge>
            <span className="flex items-center gap-1 text-xs text-emerald-500">
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
              Live
            </span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Railway-scheduled paper slips, bankroll, Discord delivery, and closing-line value
          </p>
        </div>
        <Button variant="outline" onClick={() => void refresh()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {error && <Card className="mb-6 border-destructive p-4 text-sm text-destructive">{error}</Card>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Paper Bankroll"
          value={currency.format(summary?.bankroll ?? 200)}
          detail={`Started at ${currency.format(summary?.starting_bankroll ?? 200)}`}
        />
        <MetricCard
          label="Profit / Loss"
          value={currency.format(summary?.profit ?? 0)}
          detail={`${summary?.win_rate ?? 0}% settled win rate`}
        />
        <MetricCard
          label="Open Exposure"
          value={currency.format(summary?.exposure ?? 0)}
          detail={`${summary?.open_entries ?? 0} open · ${currency.format(summary?.daily_staked ?? 0)} today`}
        />
        <MetricCard
          label="Record"
          value={`${summary?.wins ?? 0}-${summary?.losses ?? 0}-${summary?.pushes ?? 0}`}
          detail={`${summary?.entries ?? 0} total simulated slips`}
        />
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Scheduler</p>
          <p className="mt-2 font-semibold">
            {scheduler?.enabled ? (scheduler.running ? "Running" : scheduler.status || "Enabled") : "Disabled"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {scheduler?.checked_at
              ? `Last heartbeat ${new Date(scheduler.checked_at).toLocaleString()}`
              : "Waiting for Railway heartbeat"}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Daily scan budget</p>
          <p className="mt-2 font-semibold">
            {quota?.scans_today ?? 0} / {quota?.scan_cap ?? 24}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {quota?.remaining_scans ?? 0} paid scans remaining today
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Ops backlog</p>
          <p className="mt-2 font-semibold">
            {data?.delivery_failures ?? 0} delivery fails · {data?.settlement_backlog ?? 0} unsettled
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Kill switch: PAPER_SCHEDULER_ENABLED=false
          </p>
        </Card>
      </div>

      <Card className="mt-6 p-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3">
            <Activity className="h-5 w-5 text-primary" />
            <div>
              <p className="font-semibold">Latest paper automation</p>
              <p className="text-sm text-muted-foreground">
                {data?.automation.message || data?.automation.status || "Waiting for a slate"}
              </p>
            </div>
          </div>
          <div className="text-right text-xs text-muted-foreground">
            <p>{data?.automation.sport || "All supported sports"}</p>
            <p>
              {data?.automation.checked_at
                ? `Checked ${new Date(data.automation.checked_at).toLocaleString()}`
                : "Not checked yet"}
            </p>
          </div>
        </div>
      </Card>

      <div className="mb-4 mt-8 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Slip ledger</h2>
        <span className="text-xs text-muted-foreground">Updates every 10 seconds</span>
      </div>

      {!data?.entries.length ? (
        <Card className="p-12 text-center">
          <WalletCards className="mx-auto h-12 w-12 text-muted-foreground" />
          <h3 className="mt-4 text-lg font-semibold">No qualifying paper slips yet</h3>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
            This is expected when there are no nearby games or no entry clears the deterministic
            quality and risk thresholds. The bot will not force a play.
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
                  <Badge variant={entry.tier === "excellent" ? "default" : "secondary"}>
                    {entry.tier}
                  </Badge>
                  <Badge variant="secondary">PAPER</Badge>
                  <Badge variant={entry.delivery_status === "sent" ? "default" : "outline"}>
                    Discord {entry.delivery_status}
                  </Badge>
                </div>
                <div className="text-sm sm:text-right">
                  <p className="font-semibold">
                    {currency.format(entry.stake)} to return {currency.format(entry.potential_payout)}
                  </p>
                  <p className="text-muted-foreground">Expected ROI {entry.expected_roi.toFixed(2)}%</p>
                </div>
              </div>

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
                    <div className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                      <div>
                        <p className="text-muted-foreground">Win probability</p>
                        <p className="mt-1 font-medium">{leg.win_probability.toFixed(2)}%</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Books</p>
                        <p className="mt-1 font-medium">{leg.book_count}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Entry → close</p>
                        <p className="mt-1 font-medium">
                          {leg.entry_line} → {leg.closing_line ?? "pending"}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Line CLV</p>
                        <p
                          className={`mt-1 font-medium ${
                            leg.line_clv === null || leg.line_clv === undefined
                              ? ""
                              : leg.line_clv >= 0
                                ? "text-emerald-500"
                                : "text-destructive"
                          }`}
                        >
                          {leg.line_clv === null || leg.line_clv === undefined
                            ? "pending"
                            : `${leg.line_clv > 0 ? "+" : ""}${leg.line_clv}`}
                        </p>
                      </div>
                    </div>
                    {leg.probability_clv !== null && leg.probability_clv !== undefined && (
                      <p className="mt-2 text-xs text-muted-foreground">
                        Prob CLV {leg.probability_clv > 0 ? "+" : ""}
                        {leg.probability_clv}%
                      </p>
                    )}
                  </div>
                ))}
              </div>

              <div className="flex flex-col justify-between gap-2 bg-muted/30 px-5 py-3 text-xs text-muted-foreground sm:flex-row">
                <span className="flex items-center gap-1">
                  <Trophy className="h-3.5 w-3.5" />
                  {entry.status === "settled"
                    ? `${entry.result} · ${currency.format(entry.profit ?? 0)}`
                    : "Awaiting results"}
                </span>
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
