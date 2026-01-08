import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ArrowUp, ArrowDown, Check } from "lucide-react"
import type { Prop } from "@/lib/types"

interface EVPlayCardProps {
  prop: Prop
}

export function EVPlayCard({ prop }: EVPlayCardProps) {
  if (!prop.bestPlay) return null

  const { bestPlay, sharpOdds } = prop
  const evColor =
    bestPlay.evPercentage >= 5 ? "border-primary" : bestPlay.evPercentage >= 2 ? "border-accent" : "border-orange-500"

  const formatOdds = (odds: number) => (odds > 0 ? `+${odds}` : odds.toString())

  return (
    <Card className={`border-l-4 ${evColor} p-6`}>
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        {/* Left: EV Badge and Player Info */}
        <div className="space-y-3">
          <Badge variant="outline" className="font-mono text-lg font-bold">
            +{bestPlay.evPercentage.toFixed(1)}% EV
          </Badge>

          <div>
            <h3 className="text-xl font-bold">{prop.playerName}</h3>
            <div className="mt-1 flex items-center gap-4 text-sm text-muted-foreground">
              <span>
                {prop.game} •{" "}
                {new Date(prop.gameTime).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="font-semibold">
              {bestPlay.play} {bestPlay.line} {prop.stat}
            </span>
            <Badge variant="secondary">via {bestPlay.platform}</Badge>
          </div>

          <div className="flex items-center gap-4 text-sm">
            <span className="font-numeric">
              <span className="text-muted-foreground">Win%:</span>{" "}
              <span className="font-bold">{bestPlay.winProbability.toFixed(1)}%</span>
            </span>
            <span className="font-numeric text-muted-foreground">
              Book: {sharpOdds?.book} {formatOdds(sharpOdds?.overOdds || 0)}/{formatOdds(sharpOdds?.underOdds || 0)}
            </span>
          </div>
        </div>

        {/* Right: All Lines and Entry Types */}
        <div className="space-y-3 md:text-right">
          <div className="flex flex-wrap gap-2 text-sm font-numeric md:justify-end">
            <span className="text-muted-foreground">Lines:</span>
            {prop.lines.prizepicks && (
              <span className={prop.bestPlay?.platform === "PrizePicks" ? "font-bold text-primary" : ""}>
                PP {prop.lines.prizepicks}{" "}
                {prop.bestPlay?.platform === "PrizePicks" && prop.bestPlay.play === "OVER" && (
                  <ArrowUp className="inline h-3 w-3" />
                )}
                {prop.bestPlay?.platform === "PrizePicks" && prop.bestPlay.play === "UNDER" && (
                  <ArrowDown className="inline h-3 w-3" />
                )}
              </span>
            )}
            {prop.lines.underdog && (
              <span className={prop.bestPlay?.platform === "Underdog" ? "font-bold text-primary" : ""}>
                | UD {prop.lines.underdog}{" "}
                {prop.bestPlay?.platform === "Underdog" && prop.bestPlay.play === "OVER" && (
                  <ArrowUp className="inline h-3 w-3" />
                )}
                {prop.bestPlay?.platform === "Underdog" && prop.bestPlay.play === "UNDER" && (
                  <ArrowDown className="inline h-3 w-3" />
                )}
              </span>
            )}
            {prop.lines.sleeper && (
              <span className={prop.bestPlay?.platform === "Sleeper" ? "font-bold text-primary" : ""}>
                | SLP {prop.lines.sleeper}{" "}
                {prop.bestPlay?.platform === "Sleeper" && prop.bestPlay.play === "OVER" && (
                  <ArrowUp className="inline h-3 w-3" />
                )}
                {prop.bestPlay?.platform === "Sleeper" && prop.bestPlay.play === "UNDER" && (
                  <ArrowDown className="inline h-3 w-3" />
                )}
              </span>
            )}
          </div>

          <div className="flex flex-wrap gap-2 text-sm md:justify-end">
            <Badge variant="outline" className="gap-1">
              <Check className="h-3 w-3" /> 2-Power
            </Badge>
            <Badge variant="outline" className="gap-1">
              <Check className="h-3 w-3" /> 4-Power
            </Badge>
            <Badge variant="outline" className="gap-1">
              <Check className="h-3 w-3" /> 5/6-Flex
            </Badge>
          </div>
        </div>
      </div>
    </Card>
  )
}
