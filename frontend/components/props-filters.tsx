"use client"

import * as React from "react"
import { Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"

export function PropsFilters() {
  const [minWinRate, setMinWinRate] = React.useState("54")
  const [minEV, setMinEV] = React.useState("0")
  const [searchQuery, setSearchQuery] = React.useState("")
  const [selectedSports, setSelectedSports] = React.useState<string[]>(["NBA", "NFL"])
  const [selectedPlatforms, setSelectedPlatforms] = React.useState<string[]>(["PrizePicks", "Underdog", "Sleeper"])
  const [selectedStats, setSelectedStats] = React.useState<string[]>(["Points", "Rebounds", "Assists"])

  const sports = ["NBA", "NFL", "NHL", "MLB", "NCAAB", "NCAAF"]
  const platforms = ["PrizePicks", "Underdog", "Sleeper", "Betr"]
  const stats = ["Points", "Rebounds", "Assists", "3-Ptrs", "Blocks", "Steals"]

  const toggleSelection = (item: string, list: string[], setter: (list: string[]) => void) => {
    if (list.includes(item)) {
      setter(list.filter((i) => i !== item))
    } else {
      setter([...list, item])
    }
  }

  return (
    <div className="mb-6 space-y-4 rounded-lg border border-border bg-card p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Filters</h2>

      {/* Filter Row 1 */}
      <div className="flex flex-wrap gap-3">
        {/* Sport Filter */}
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="min-w-[140px] justify-start bg-transparent">
              Sport ▼
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-56" align="start">
            <div className="space-y-2">
              {sports.map((sport) => (
                <div key={sport} className="flex items-center space-x-2">
                  <Checkbox
                    id={`sport-${sport}`}
                    checked={selectedSports.includes(sport)}
                    onCheckedChange={() => toggleSelection(sport, selectedSports, setSelectedSports)}
                  />
                  <Label htmlFor={`sport-${sport}`} className="text-sm font-normal cursor-pointer">
                    {sport}
                  </Label>
                </div>
              ))}
            </div>
          </PopoverContent>
        </Popover>

        {/* Platform Filter */}
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="min-w-[140px] justify-start bg-transparent">
              Platform ▼
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-56" align="start">
            <div className="space-y-2">
              {platforms.map((platform) => (
                <div key={platform} className="flex items-center space-x-2">
                  <Checkbox
                    id={`platform-${platform}`}
                    checked={selectedPlatforms.includes(platform)}
                    onCheckedChange={() => toggleSelection(platform, selectedPlatforms, setSelectedPlatforms)}
                  />
                  <Label htmlFor={`platform-${platform}`} className="text-sm font-normal cursor-pointer">
                    {platform}
                  </Label>
                </div>
              ))}
            </div>
          </PopoverContent>
        </Popover>

        {/* Stat Filter */}
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="min-w-[140px] justify-start bg-transparent">
              Stat ▼
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-56" align="start">
            <div className="space-y-2">
              {stats.map((stat) => (
                <div key={stat} className="flex items-center space-x-2">
                  <Checkbox
                    id={`stat-${stat}`}
                    checked={selectedStats.includes(stat)}
                    onCheckedChange={() => toggleSelection(stat, selectedStats, setSelectedStats)}
                  />
                  <Label htmlFor={`stat-${stat}`} className="text-sm font-normal cursor-pointer">
                    {stat}
                  </Label>
                </div>
              ))}
            </div>
          </PopoverContent>
        </Popover>

        {/* Team Filter */}
        <Select defaultValue="all">
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Team" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Teams</SelectItem>
            <SelectItem value="lal">Lakers</SelectItem>
            <SelectItem value="bos">Celtics</SelectItem>
          </SelectContent>
        </Select>

        {/* Game Filter */}
        <Select defaultValue="all">
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Game" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Games</SelectItem>
            <SelectItem value="lal-bos">LAL@BOS</SelectItem>
            <SelectItem value="mia-nyk">MIA@NYK</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Filter Row 2 */}
      <div className="flex flex-wrap items-end gap-3">
        {/* Min Win% */}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="min-win" className="text-xs">
            Min Win%
          </Label>
          <Input
            id="min-win"
            type="number"
            value={minWinRate}
            onChange={(e) => setMinWinRate(e.target.value)}
            className="w-[120px]"
          />
        </div>

        {/* Min EV% */}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="min-ev" className="text-xs">
            Min EV%
          </Label>
          <Input
            id="min-ev"
            type="number"
            value={minEV}
            onChange={(e) => setMinEV(e.target.value)}
            className="w-[120px]"
          />
        </div>

        {/* Search Player */}
        <div className="flex flex-col gap-1.5 flex-1 min-w-[200px]">
          <Label htmlFor="search-player" className="text-xs">
            Search Player
          </Label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="search-player"
              type="search"
              placeholder="Search player..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-2">
        <Button size="sm">Apply Filters</Button>
        <Button size="sm" variant="outline">
          Reset
        </Button>
        <Button size="sm" variant="default" className="bg-primary">
          Show +EV Only
        </Button>
        <Button size="sm" variant="outline">
          Export CSV
        </Button>
      </div>
    </div>
  )
}
