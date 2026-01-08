"use client"

import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function EVPlayFilters() {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="w-32 space-y-2">
          <Label htmlFor="min-ev" className="text-xs">
            Min EV%
          </Label>
          <Input id="min-ev" type="number" defaultValue="2" className="h-9" />
        </div>

        <div className="w-32 space-y-2">
          <Label htmlFor="min-win" className="text-xs">
            Min Win%
          </Label>
          <Input id="min-win" type="number" defaultValue="54" className="h-9" />
        </div>

        <div className="flex-1 space-y-2">
          <Label htmlFor="platform-filter" className="text-xs">
            Platform
          </Label>
          <Select defaultValue="all">
            <SelectTrigger id="platform-filter" className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Platforms</SelectItem>
              <SelectItem value="prizepicks">PrizePicks</SelectItem>
              <SelectItem value="underdog">Underdog</SelectItem>
              <SelectItem value="sleeper">Sleeper</SelectItem>
              <SelectItem value="betr">Betr</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex-1 space-y-2">
          <Label htmlFor="sport-filter" className="text-xs">
            Sport
          </Label>
          <Select defaultValue="all">
            <SelectTrigger id="sport-filter" className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sports</SelectItem>
              <SelectItem value="nba">NBA</SelectItem>
              <SelectItem value="nfl">NFL</SelectItem>
              <SelectItem value="nhl">NHL</SelectItem>
              <SelectItem value="mlb">MLB</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button variant="default" className="h-9">
          Apply Filters
        </Button>
        <Button variant="outline" className="h-9 bg-transparent">
          Reset
        </Button>
      </div>
    </div>
  )
}
