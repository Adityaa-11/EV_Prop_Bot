import Link from "next/link"
import { Clock, MapPin, TrendingUp, List } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { Game } from "@/lib/types"
import { cn } from "@/lib/utils"

interface GameCardProps {
  game: Game
}

export function GameCard({ game }: GameCardProps) {
  const gameTime = new Date(game.startTime)
  const formattedTime = gameTime.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  })

  const hasStarted = gameTime < new Date()

  return (
    <Card className="overflow-hidden transition-all hover:shadow-lg">
      <CardContent className="p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          {/* Game Info */}
          <div className="flex-1 space-y-3">
            {/* Teams */}
            <div className="flex items-center gap-3">
              <h3 className="text-xl font-bold">
                {game.awayTeam.abbreviation} @ {game.homeTeam.abbreviation}
              </h3>
              {hasStarted && (
                <Badge variant="destructive" className="text-xs">
                  Started
                </Badge>
              )}
            </div>

            {/* Full Team Names */}
            <p className="text-sm text-muted-foreground">
              {game.awayTeam.name} vs {game.homeTeam.name}
            </p>

            {/* Game Details */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <Clock className="h-4 w-4" />
                <span>{formattedTime}</span>
              </div>
              {game.venue && (
                <div className="flex items-center gap-1.5">
                  <MapPin className="h-4 w-4" />
                  <span>{game.venue}</span>
                </div>
              )}
              {game.tvChannel && (
                <Badge variant="secondary" className="text-xs">
                  {game.tvChannel}
                </Badge>
              )}
            </div>

            {/* Top EV Play Preview */}
            {game.topEvPlay && (
              <div className="rounded-md bg-primary/10 p-3 border border-primary/20">
                <p className="text-sm font-medium text-foreground">
                  <span className="text-primary">Top +EV:</span> {game.topEvPlay.playerName} {game.topEvPlay.play}{" "}
                  {game.topEvPlay.line} {game.topEvPlay.stat}
                </p>
                <div className="mt-1 flex items-center gap-3 text-sm">
                  <span className="font-mono text-primary font-semibold">
                    {game.topEvPlay.winProbability.toFixed(1)}% Win
                  </span>
                  <span className="font-mono text-primary font-semibold">
                    +{game.topEvPlay.evPercentage.toFixed(1)}% EV
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Stats & Action */}
          <div className="flex flex-row items-center gap-4 sm:flex-col sm:items-end">
            {/* Stats */}
            <div className="flex flex-col gap-2 text-right">
              <div className="flex items-center gap-2">
                <List className="h-4 w-4 text-muted-foreground" />
                <div>
                  <span className="font-mono text-lg font-bold">{game.propCount}</span>
                  <span className="ml-1 text-sm text-muted-foreground">props</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-primary" />
                <div>
                  <span className={cn("font-mono text-lg font-bold", game.evPlayCount > 0 && "text-primary")}>
                    {game.evPlayCount}
                  </span>
                  <span className="ml-1 text-sm text-muted-foreground">+EV</span>
                </div>
              </div>
            </div>

            {/* View Button */}
            <Link href={`/props?game=${game.id}`}>
              <Button className="whitespace-nowrap">View Props</Button>
            </Link>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
