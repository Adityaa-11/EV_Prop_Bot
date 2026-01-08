import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { MiddleOpportunity } from "@/lib/types"

interface MiddleCardProps {
  middle: MiddleOpportunity
}

export function MiddleCard({ middle }: MiddleCardProps) {
  return (
    <Card className="p-6">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <Badge variant="outline" className="text-sm font-semibold">
            MIDDLE OPPORTUNITY
          </Badge>
          <Badge variant="secondary" className="font-mono">
            {middle.spreadSize} pt spread
          </Badge>
        </div>

        {/* Player and Game Info */}
        <div>
          <h3 className="text-xl font-bold">
            {middle.playerName} - {middle.statType}
          </h3>
          <p className="text-sm text-muted-foreground">
            {middle.gameInfo} •{" "}
            {new Date(middle.gameTime).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
          </p>
        </div>

        {/* Platform Comparison */}
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="border-2 border-primary/50 bg-card p-4">
            <h4 className="mb-2 font-semibold uppercase text-primary">{middle.platformA.name}</h4>
            <div className="space-y-1 text-sm">
              <p>
                <span className="text-muted-foreground">Line:</span>{" "}
                <span className="font-mono font-bold">{middle.platformA.line}</span>
              </p>
              <p>
                <span className="text-muted-foreground">Play:</span>{" "}
                <span className="font-semibold">{middle.platformA.recommendedPlay}</span>
              </p>
            </div>
          </Card>

          <Card className="border-2 border-secondary/50 bg-card p-4">
            <h4 className="mb-2 font-semibold uppercase text-secondary">{middle.platformB.name}</h4>
            <div className="space-y-1 text-sm">
              <p>
                <span className="text-muted-foreground">Line:</span>{" "}
                <span className="font-mono font-bold">{middle.platformB.line}</span>
              </p>
              <p>
                <span className="text-muted-foreground">Play:</span>{" "}
                <span className="font-semibold">{middle.platformB.recommendedPlay}</span>
              </p>
            </div>
          </Card>
        </div>

        {/* Middle Zone */}
        <div className="rounded-lg bg-muted p-4">
          <p className="mb-2 text-sm font-semibold">Middle Zone: {middle.middleZone.join(", ")}</p>
          <p className="text-sm font-bold text-primary">
            If {middle.playerName.split(" ")[1]} scores exactly {middle.middleZone[0]} → BOTH BETS WIN
          </p>
        </div>

        {/* Outcome Analysis */}
        <div className="space-y-2 text-sm">
          <p className="font-semibold">Outcome Analysis:</p>
          <ul className="space-y-1 text-muted-foreground">
            <li>
              • {middle.playerName.split(" ")[1]} {"<"} {middle.middleZone[0]}: {middle.platformA.name} wins,{" "}
              {middle.platformB.name} loses (small loss)
            </li>
            <li className="text-primary">
              • {middle.playerName.split(" ")[1]} = {middle.middleZone[0]}: {middle.platformA.name} wins,{" "}
              {middle.platformB.name} wins (big profit!)
            </li>
            <li>
              • {middle.playerName.split(" ")[1]} {">"} {middle.middleZone[0]}: {middle.platformA.name} loses,{" "}
              {middle.platformB.name} wins (small loss)
            </li>
          </ul>
        </div>
      </div>
    </Card>
  )
}
