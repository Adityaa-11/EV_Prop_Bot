"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { CheckCircle2, XCircle, Loader2, RefreshCw, AlertTriangle, Key } from "lucide-react"
import { checkHealth, getOddsUsage, getAllKeysUsage, rotateKey, setKey, type HealthResponse, type OddsUsageResponse, type AllKeysUsageResponse } from "@/lib/api"
import { Progress } from "@/components/ui/progress"

export default function SettingsPage() {
  const [health, setHealth] = React.useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = React.useState(true)
  const [healthError, setHealthError] = React.useState<string | null>(null)
  const [oddsUsage, setOddsUsage] = React.useState<OddsUsageResponse | null>(null)
  const [usageLoading, setUsageLoading] = React.useState(true)
  const [adminKey, setAdminKey] = React.useState("")
  const [allKeys, setAllKeys] = React.useState<AllKeysUsageResponse | null>(null)
  const [allKeysLoading, setAllKeysLoading] = React.useState(false)
  const [allKeysError, setAllKeysError] = React.useState<string | null>(null)
  const [keyActionLoading, setKeyActionLoading] = React.useState(false)

  React.useEffect(() => {
    const saved = window.localStorage.getItem("ev_admin_api_key")
    if (saved) setAdminKey(saved)
  }, [])

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

  const fetchOddsUsage = async () => {
    setUsageLoading(true)
    try {
      const result = await getOddsUsage()
      setOddsUsage(result)
    } catch (err) {
      console.error("Failed to fetch odds usage:", err)
    } finally {
      setUsageLoading(false)
    }
  }

  const fetchAllKeys = async () => {
    if (!adminKey.trim()) {
      setAllKeysError("Paste your ADMIN_API_KEY first")
      return
    }
    setAllKeysLoading(true)
    setAllKeysError(null)
    try {
      window.localStorage.setItem("ev_admin_api_key", adminKey.trim())
      const result = await getAllKeysUsage(adminKey.trim())
      setAllKeys(result)
    } catch (err) {
      setAllKeys(null)
      setAllKeysError(err instanceof Error ? err.message : "Failed to load key usage")
    } finally {
      setAllKeysLoading(false)
    }
  }

  const handleRotate = async () => {
    if (!adminKey.trim()) return
    setKeyActionLoading(true)
    try {
      await rotateKey(adminKey.trim())
      await fetchAllKeys()
      await fetchOddsUsage()
    } catch (err) {
      setAllKeysError(err instanceof Error ? err.message : "Rotate failed")
    } finally {
      setKeyActionLoading(false)
    }
  }

  const handleSetKey = async (keyIndex: number) => {
    if (!adminKey.trim()) return
    setKeyActionLoading(true)
    try {
      await setKey(keyIndex, adminKey.trim())
      await fetchAllKeys()
      await fetchOddsUsage()
    } catch (err) {
      setAllKeysError(err instanceof Error ? err.message : "Set key failed")
    } finally {
      setKeyActionLoading(false)
    }
  }

  React.useEffect(() => {
    checkApiHealth()
    fetchOddsUsage()
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

        {/* Odds API Usage */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Odds API Usage</CardTitle>
                <CardDescription>Monthly API request quota (resets every month)</CardDescription>
              </div>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={fetchOddsUsage} 
                disabled={usageLoading}
                className="gap-1"
              >
                <RefreshCw className={`h-3 w-3 ${usageLoading ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {usageLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : oddsUsage?.error ? (
              <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                <p className="font-medium">Error</p>
                <p className="mt-1">{oddsUsage.error}</p>
              </div>
            ) : oddsUsage?.configured ? (
              <>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Requests Used</span>
                    <span className="font-mono font-semibold">
                      {oddsUsage.requests_used} / {oddsUsage.requests_total}
                    </span>
                  </div>
                  <Progress 
                    value={((oddsUsage.requests_used || 0) / (oddsUsage.requests_total || 500)) * 100} 
                    className="h-3"
                  />
                </div>

                <div className="grid gap-4 pt-2 sm:grid-cols-3">
                  <div className="rounded-lg bg-muted p-3">
                    <Label className="text-xs text-muted-foreground">Used</Label>
                    <div className="mt-1 font-mono text-2xl font-bold text-orange-500">
                      {oddsUsage.requests_used}
                    </div>
                  </div>
                  <div className="rounded-lg bg-muted p-3">
                    <Label className="text-xs text-muted-foreground">Remaining</Label>
                    <div className={`mt-1 font-mono text-2xl font-bold ${
                      (oddsUsage.requests_remaining || 0) < 50 
                        ? "text-red-500" 
                        : (oddsUsage.requests_remaining || 0) < 150 
                          ? "text-yellow-500" 
                          : "text-green-500"
                    }`}>
                      {oddsUsage.requests_remaining}
                    </div>
                  </div>
                  <div className="rounded-lg bg-muted p-3">
                    <Label className="text-xs text-muted-foreground">Monthly Limit</Label>
                    <div className="mt-1 font-mono text-2xl font-bold">
                      {oddsUsage.requests_total}
                    </div>
                  </div>
                </div>

                {oddsUsage.auto_rotation && (
                  <div className="rounded-md bg-muted p-3 text-sm">
                    <p>
                      Auto-rotation:{" "}
                      <span className="font-semibold">
                        {oddsUsage.auto_rotation.enabled ? "on" : "off"}
                      </span>
                      {" · "}
                      current key {oddsUsage.auto_rotation.current_key}/
                      {oddsUsage.auto_rotation.total_keys}
                    </p>
                    {oddsUsage.message && (
                      <p className="mt-1 text-amber-600 dark:text-amber-400">{oddsUsage.message}</p>
                    )}
                  </div>
                )}

                {(oddsUsage.requests_remaining || 0) < 50 && (
                  <div className="flex items-center gap-2 rounded-md bg-yellow-500/10 p-3 text-sm text-yellow-600 dark:text-yellow-400">
                    <AlertTriangle className="h-4 w-4" />
                    <span>Running low on API requests! Check all keys below or add fresh Odds API keys.</span>
                  </div>
                )}
              </>
            ) : (
              <div className="rounded-md bg-muted p-3 text-sm text-muted-foreground">
                Odds API key not configured. Set <code className="rounded bg-background px-1 py-0.5">ODDS_API_KEY</code> in your .env file.
              </div>
            )}
          </CardContent>
        </Card>

        {/* API Key Manager */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Key className="h-5 w-5" />
              API Key Manager
            </CardTitle>
            <CardDescription>
              View remaining quota for every Odds API key and force rotate. Requires Railway{" "}
              <code className="rounded bg-muted px-1">ADMIN_API_KEY</code>.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
              <div className="space-y-2">
                <Label htmlFor="admin-key">Admin API Key</Label>
                <Input
                  id="admin-key"
                  type="password"
                  value={adminKey}
                  onChange={(e) => setAdminKey(e.target.value)}
                  placeholder="Paste ADMIN_API_KEY"
                  autoComplete="off"
                />
              </div>
              <div className="flex items-end">
                <Button onClick={() => void fetchAllKeys()} disabled={allKeysLoading || !adminKey.trim()}>
                  {allKeysLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                  Load all keys
                </Button>
              </div>
              <div className="flex items-end">
                <Button
                  variant="outline"
                  onClick={() => void handleRotate()}
                  disabled={keyActionLoading || !adminKey.trim()}
                >
                  Rotate
                </Button>
              </div>
            </div>

            {allKeysError && (
              <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{allKeysError}</div>
            )}

            {allKeys && (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                  <span>
                    Current key <span className="font-semibold text-foreground">{allKeys.current_key}</span> /{" "}
                    {allKeys.total_keys}
                  </span>
                  <span>
                    Total remaining{" "}
                    <span className="font-semibold text-foreground">{allKeys.total_remaining}</span>
                  </span>
                </div>
                <div className="space-y-2">
                  {allKeys.keys.map((key) => (
                    <div
                      key={key.key_number}
                      className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">Key {key.key_number}</span>
                          <Badge
                            variant={key.status === "active" ? "default" : "outline"}
                            className={key.status === "active" ? "bg-green-600" : ""}
                          >
                            {key.status}
                          </Badge>
                          {key.key_number === allKeys.current_key && (
                            <Badge variant="secondary">current</Badge>
                          )}
                        </div>
                        <p className="mt-1 font-mono text-xs text-muted-foreground">{key.key_preview}</p>
                        <p className="mt-1 text-sm">
                          {key.requests_remaining} remaining · {key.requests_used} used
                        </p>
                        {key.error && <p className="text-xs text-destructive">{key.error}</p>}
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={keyActionLoading || key.status === "invalid"}
                        onClick={() => void handleSetKey(key.key_number)}
                      >
                        Use
                      </Button>
                    </div>
                  ))}
                </div>
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
