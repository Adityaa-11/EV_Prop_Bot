"use client"

import * as React from "react"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"

export function GameFilters() {
  const [hideStarted, setHideStarted] = React.useState(false)

  return (
    <div className="mb-6 flex flex-wrap items-center gap-4">
      <div className="flex items-center gap-2">
        <Label htmlFor="sport-filter" className="text-sm font-medium">
          Sport:
        </Label>
        <Select defaultValue="all">
          <SelectTrigger id="sport-filter" className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sports</SelectItem>
            <SelectItem value="nba">NBA</SelectItem>
            <SelectItem value="nfl">NFL</SelectItem>
            <SelectItem value="nhl">NHL</SelectItem>
            <SelectItem value="mlb">MLB</SelectItem>
            <SelectItem value="ncaab">NCAAB</SelectItem>
            <SelectItem value="ncaaf">NCAAF</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <Label htmlFor="platform-filter" className="text-sm font-medium">
          Platform:
        </Label>
        <Select defaultValue="all">
          <SelectTrigger id="platform-filter" className="w-[180px]">
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

      <div className="flex items-center gap-2">
        <Checkbox
          id="hide-started"
          checked={hideStarted}
          onCheckedChange={(checked) => setHideStarted(checked === true)}
        />
        <Label htmlFor="hide-started" className="text-sm font-medium cursor-pointer">
          Hide Started
        </Label>
      </div>
    </div>
  )
}
