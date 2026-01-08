"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { CheckCircle2, XCircle, Loader2 } from "lucide-react"
import { checkHealth, type HealthResponse } from "@/lib/api"

export default function SettingsPage() {
  const [health, setHealth] = React.useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = React.useState(true)
  const [healthError, setHealthError] = React.useState<string | null>(null)

  const checkApiHealth = async () => {
    setHealthLoading(true)
    setHealthError(null)
    try {
      const result = await checkHealth()
      setHealth(result)
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : "Failed to connect")
    } finally {
      setHealthLoading(false)
    }
  }

  React.useEffect(() => {
    checkApiHealth()
  }, [])

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6">
      {/* Page Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">Configure your dashboard preferences</p>
      </div>

      <div className="space-y-6">
        {/* API Status */}
        <Card>
          <CardHeader>
            <CardTitle>API Status</CardTitle>
            <CardDescription>Connection to the EV Dashboard API</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <Label>API Server</Label>
                <p className="text-sm text-muted-foreground font-mono">
                  {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {healthLoading ? (
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                ) : healthError ? (
                  <Badge variant="destructive" className="gap-1">
                    <XCircle className="h-3 w-3" />
                    Disconnected
                  </Badge>
                ) : (
                  <Badge variant="default" className="gap-1 bg-green-600">
                    <CheckCircle2 className="h-3 w-3" />
                    Connected
                  </Badge>
                )}
                <Button variant="outline" size="sm" onClick={checkApiHealth} disabled={healthLoading}>
                  Test
                </Button>
              </div>
            </div>

            {health && (
              <div className="grid gap-4 pt-4 border-t sm:grid-cols-2">
                <div>
                  <Label className="text-xs text-muted-foreground">Odds API</Label>
                  <div className="mt-1 flex items-center gap-2">
                    {health.odds_api_configured ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                    ) : (
                      <XCircle className="h-4 w-4 text-red-500" />
                    )}
                    <span className="text-sm">
                      {health.odds_api_configured ? "Configured" : "Not configured"}
                    </span>
                  </div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Sharp Books</Label>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {health.sharp_books.map((book) => (
                      <Badge key={book} variant="secondary" className="text-xs capitalize">
                        {book}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="sm:col-span-2">
                  <Label className="text-xs text-muted-foreground">Platforms</Label>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {Object.entries(health.platforms).map(([platform, active]) => (
                      <Badge
                        key={platform}
                        variant={active ? "default" : "outline"}
                        className={active ? "bg-green-600" : ""}
                      >
                        {platform}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {healthError && (
              <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                <p className="font-medium">Connection Error</p>
                <p className="mt-1">{healthError}</p>
                <p className="mt-2 text-xs">Make sure the API server is running and accessible.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Display Preferences */}
        <Card>
          <CardHeader>
            <CardTitle>Display Preferences</CardTitle>
            <CardDescription>Customize how data is displayed</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="timezone">Timezone</Label>
                <Select defaultValue="america-new-york">
                  <SelectTrigger id="timezone">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="america-new-york">America/New_York</SelectItem>
                    <SelectItem value="america-chicago">America/Chicago</SelectItem>
                    <SelectItem value="america-denver">America/Denver</SelectItem>
                    <SelectItem value="america-los-angeles">America/Los_Angeles</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="default-sport">Default Sport</Label>
                <Select defaultValue="nba">
                  <SelectTrigger id="default-sport">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="nba">NBA</SelectItem>
                    <SelectItem value="nfl">NFL</SelectItem>
                    <SelectItem value="nhl">NHL</SelectItem>
                    <SelectItem value="mlb">MLB</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Odds Format</Label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2">
                  <input type="radio" name="odds-format" value="american" defaultChecked className="text-primary" />
                  <span className="text-sm">American</span>
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="odds-format" value="decimal" className="text-primary" />
                  <span className="text-sm">Decimal</span>
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="odds-format" value="fractional" className="text-primary" />
                  <span className="text-sm">Fractional</span>
                </label>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* EV Thresholds */}
        <Card>
          <CardHeader>
            <CardTitle>Break-Even Reference</CardTitle>
            <CardDescription>Platform break-even percentages for different slip types</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <Card className="border-muted">
                <CardContent className="pt-4">
                  <h4 className="mb-3 font-semibold">PrizePicks</h4>
                  <div className="grid gap-3 text-sm sm:grid-cols-3">
                    <div>
                      <Label className="text-xs text-muted-foreground">5/6-Flex</Label>
                      <div className="mt-1 font-mono text-lg">54.34%</div>
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground">4-Power</Label>
                      <div className="mt-1 font-mono text-lg">56.23%</div>
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground">2-Power</Label>
                      <div className="mt-1 font-mono text-lg">57.74%</div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-muted">
                <CardContent className="pt-4">
                  <h4 className="mb-3 font-semibold">Underdog</h4>
                  <div className="grid gap-3 text-sm sm:grid-cols-4">
                    <div>
                      <Label className="text-xs text-muted-foreground">5-Leg</Label>
                      <div className="mt-1 font-mono text-lg">52.38%</div>
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground">4-Leg</Label>
                      <div className="mt-1 font-mono text-lg">53.57%</div>
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground">3-Leg</Label>
                      <div className="mt-1 font-mono text-lg">55.56%</div>
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground">2-Leg</Label>
                      <div className="mt-1 font-mono text-lg">60.00%</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </CardContent>
        </Card>

        {/* Discord Integration Info */}
        <Card>
          <CardHeader>
            <CardTitle>Discord Integration</CardTitle>
            <CardDescription>Webhook alerts are configured on the backend</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Discord webhook URLs are configured in the backend <code className="rounded bg-muted px-1 py-0.5">.env</code> file.
              The Discord bot can send +EV alerts to your configured channels.
            </p>
            <div className="rounded-md bg-muted p-3">
              <p className="text-xs font-medium">Bot Commands:</p>
              <ul className="mt-2 space-y-1 font-mono text-xs text-muted-foreground">
                <li>!ev nba - Get PrizePicks +EV plays</li>
                <li>!ud nba - Get Underdog +EV plays</li>
                <li>!both nba - Get from both platforms</li>
                <li>!webhook both nba - Post to webhooks</li>
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
