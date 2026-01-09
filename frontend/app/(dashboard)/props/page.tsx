"use client"

import { useEffect, useState } from "react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { RefreshCw, Loader2, AlertCircle, Search } from "lucide-react"
import { getProps, type PropsResponse, type ApiProp } from "@/lib/api"

export default function PropsPage() {
  const [data, setData] = useState<PropsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sport, setSport] = useState("all")
  const [platform, setPlatform] = useState<string | undefined>(undefined)
  const [search, setSearch] = useState("")

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getProps({ 
        sport, 
        platform,
        player: search || undefined 
      })
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

  const handleSearch = () => {
    fetchData()
  }

  // Filter props locally for instant search
  const filteredProps = data?.props.filter(prop => 
    !search || prop.player_name.toLowerCase().includes(search.toLowerCase())
  ) || []

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6">
      {/* Page Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold">All Props</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {loading ? "Loading..." : `${filteredProps.length} props available`}
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

        <div className="flex gap-2">
          <Input
            placeholder="Search player..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="w-48"
          />
          <Button variant="secondary" size="icon" onClick={handleSearch}>
            <Search className="h-4 w-4" />
          </Button>
        </div>
      </div>

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
      {!loading && !error && filteredProps.length === 0 && (
        <Card className="p-12 text-center">
          <p className="text-lg font-medium">No props found</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Try a different sport or check back when games are scheduled
          </p>
        </Card>
      )}

      {/* Props Table */}
      {!loading && !error && filteredProps.length > 0 && (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Player</TableHead>
                <TableHead>Team</TableHead>
                <TableHead>Stat</TableHead>
                <TableHead className="text-right">Line</TableHead>
                <TableHead>Platform</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredProps.slice(0, 100).map((prop, idx) => (
                <TableRow key={`${prop.id}-${idx}`}>
                  <TableCell className="font-medium">{prop.player_name}</TableCell>
                  <TableCell>{prop.team}</TableCell>
                  <TableCell>{prop.stat_type}</TableCell>
                  <TableCell className="text-right font-mono">{prop.line}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="capitalize">
                      {prop.platform}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {filteredProps.length > 100 && (
            <div className="border-t p-4 text-center text-sm text-muted-foreground">
              Showing 100 of {filteredProps.length} props
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
