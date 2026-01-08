import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { TrendingDown, TrendingUp } from "lucide-react"
import type { LineMovement } from "@/lib/types"

interface LineMovementCardProps {
  movement: LineMovement
}

export function LineMovementCard({ movement }: LineMovementCardProps) {
  return (
    <Card className="p-6">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold">
              {movement.playerName} - {movement.statType}
            </h3>
            <p className="text-sm text-muted-foreground">
              {movement.gameInfo} •{" "}
              {new Date(movement.gameTime).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
            </p>
          </div>
          <Badge variant="outline" className="font-numeric">
            {movement.minutesAgo} min ago
          </Badge>
        </div>

        {/* Movements */}
        <div className="space-y-2">
          {movement.movements.map((mov, index) => (
            <div key={index} className="flex items-center gap-2 font-mono text-sm">
              <span className="w-28 font-semibold">{mov.platform}:</span>
              <span className="text-muted-foreground">{mov.oldLine}</span>
              <span>→</span>
              <span className="font-bold">{mov.newLine}</span>
              <Badge variant={mov.change < 0 ? "destructive" : "default"} className="ml-2 gap-1">
                {mov.change < 0 ? <TrendingDown className="h-3 w-3" /> : <TrendingUp className="h-3 w-3" />}
                {mov.change > 0 ? "+" : ""}
                {mov.change.toFixed(1)}
              </Badge>
            </div>
          ))}
        </div>

        {/* Analysis */}
        <div className="rounded-lg bg-muted p-3 text-sm">
          <p className="font-medium text-foreground">{movement.analysis}</p>
        </div>
      </div>
    </Card>
  )
}
