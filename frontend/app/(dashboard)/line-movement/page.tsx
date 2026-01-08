"use client"

import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Activity, Clock } from "lucide-react"

export default function LineMovementPage() {
  return (
    <div className="container mx-auto px-4 py-6 sm:px-6">
      {/* Page Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Line Movement</h1>
        <p className="mt-1 text-sm text-muted-foreground">Track line changes across platforms</p>
      </div>

      {/* Coming Soon */}
      <Card className="p-12 text-center">
        <Activity className="mx-auto h-16 w-16 text-muted-foreground" />
        <h2 className="mt-6 text-2xl font-bold">Coming Soon</h2>
        <p className="mx-auto mt-3 max-w-md text-muted-foreground">
          Line movement tracking requires storing historical data. This feature will be available 
          once database integration is added.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Badge variant="secondary">
            <Clock className="mr-1 h-3 w-3" />
            Track line changes
          </Badge>
          <Badge variant="secondary">
            <Activity className="mr-1 h-3 w-3" />
            Sharp money indicators
          </Badge>
        </div>
      </Card>

      {/* What it will show */}
      <Card className="mt-6 border-dashed p-6">
        <h3 className="mb-4 font-semibold">What Line Movement Tracking Will Include:</h3>
        <ul className="space-y-2 text-sm text-muted-foreground">
          <li>• Historical line changes across PrizePicks, Underdog, and sportsbooks</li>
          <li>• Alerts when lines move significantly (steam moves)</li>
          <li>• Correlation between platform line changes</li>
          <li>• Sharp money indicators based on reverse line movement</li>
          <li>• Time-based charts showing line history</li>
        </ul>
      </Card>
    </div>
  )
}
