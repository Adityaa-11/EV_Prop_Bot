"use client"
import { ArrowUpRight, ArrowDownRight } from "lucide-react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import type { Prop } from "@/lib/types"
import { cn } from "@/lib/utils"

interface PropDetailDialogProps {
  prop: Prop
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function PropDetailDialog({ prop, open, onOpenChange }: PropDetailDialogProps) {
  const breakEvenRates = {
    flex5or6: 54.34,
    power4: 56.23,
    power2: 57.74,
  }

  const platforms = [
    { name: "PrizePicks", line: prop.lines.prizepicks },
    { name: "Underdog", line: prop.lines.underdog },
    { name: "Sleeper", line: prop.lines.sleeper },
    { name: "Betr", line: prop.lines.betr },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl">
            {prop.playerName} - {prop.stat}
          </DialogTitle>
        </DialogHeader>

        <div className="grid gap-6 md:grid-cols-2">
          {/* Left Column - Platform Lines */}
          <div className="space-y-4">
            <div>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Platform Lines
              </h3>
              <Card>
                <CardContent className="p-4">
                  <div className="space-y-3">
                    {platforms.map((platform) => (
                      <div key={platform.name} className="flex items-center justify-between">
                        <span className="text-sm">{platform.name}</span>
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-semibold">{platform.line ?? "--"}</span>
                          {prop.bestPlay?.platform === platform.name && platform.line !== null && (
                            <Badge className="bg-primary text-primary-foreground">⭐ BEST</Badge>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Recommendation */}
            {prop.bestPlay && (
              <div>
                <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Recommendation
                </h3>
                <Card className="border-primary">
                  <CardContent className="p-4">
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <Badge className="bg-primary text-primary-foreground text-base px-3 py-1">
                          {prop.bestPlay.platform.toUpperCase()} {prop.bestPlay.play} {prop.bestPlay.line}
                        </Badge>
                        {prop.bestPlay.play === "OVER" ? (
                          <ArrowUpRight className="h-5 w-5 text-primary" />
                        ) : (
                          <ArrowDownRight className="h-5 w-5 text-secondary" />
                        )}
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <p className="text-xs text-muted-foreground">Win Probability</p>
                          <p className="font-mono text-xl font-bold text-primary">
                            {prop.bestPlay.winProbability.toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Expected Value</p>
                          <p className="font-mono text-xl font-bold text-primary">
                            +{prop.bestPlay.evPercentage.toFixed(1)}%
                          </p>
                        </div>
                      </div>

                      <div className="pt-2 border-t border-border">
                        <p className="text-sm">
                          <span className="font-semibold">Good for:</span>
                          {prop.bestPlay.winProbability >= breakEvenRates.power2 && " 2-Power,"}
                          {prop.bestPlay.winProbability >= breakEvenRates.power4 && " 4-Power,"}
                          {prop.bestPlay.winProbability >= breakEvenRates.flex5or6 && " 5/6-Flex"}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>

          {/* Right Column - Sharp Odds */}
          <div className="space-y-4">
            {prop.sharpOdds && (
              <>
                <div>
                  <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    Sharp Odds ({prop.sharpOdds.book})
                  </h3>
                  <Card>
                    <CardContent className="p-4">
                      <div className="space-y-3">
                        <div className="flex justify-between items-center">
                          <span className="text-sm">Line:</span>
                          <span className="font-mono font-semibold text-lg">{prop.sharpOdds.line}</span>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <p className="text-xs text-muted-foreground">Over</p>
                            <p className="font-mono font-semibold">
                              {prop.sharpOdds.overOdds > 0 ? "+" : ""}
                              {prop.sharpOdds.overOdds}
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              ({prop.sharpOdds.overImplied.toFixed(1)}% implied)
                            </p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground">Under</p>
                            <p className="font-mono font-semibold">
                              {prop.sharpOdds.underOdds > 0 ? "+" : ""}
                              {prop.sharpOdds.underOdds}
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              ({prop.sharpOdds.underImplied.toFixed(1)}% implied)
                            </p>
                          </div>
                        </div>
                        <div className="pt-2 border-t border-border">
                          <p className="text-sm font-semibold mb-2">No-Vig True Odds:</p>
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <p className="text-xs text-muted-foreground">Over:</p>
                              <p className="font-mono font-semibold text-primary">
                                {prop.sharpOdds.noVigOverProb.toFixed(1)}%
                              </p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground">Under:</p>
                              <p className="font-mono font-semibold text-secondary">
                                {prop.sharpOdds.noVigUnderProb.toFixed(1)}%
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Break-Even Reference */}
                <div>
                  <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    Break-Even Reference
                  </h3>
                  <Card>
                    <CardContent className="p-4">
                      <div className="space-y-2">
                        {[
                          { name: "5/6-Flex", rate: breakEvenRates.flex5or6 },
                          { name: "4-Power", rate: breakEvenRates.power4 },
                          { name: "2-Power", rate: breakEvenRates.power2 },
                        ].map(({ name, rate }) => {
                          const clears = prop.bestPlay && prop.bestPlay.winProbability >= rate
                          return (
                            <div key={name} className="flex items-center justify-between text-sm">
                              <span>{name}:</span>
                              <div className="flex items-center gap-2">
                                <span className="font-mono">{rate.toFixed(2)}%</span>
                                <Badge
                                  variant={clears ? "default" : "secondary"}
                                  className={cn("text-xs", clears && "bg-primary text-primary-foreground")}
                                >
                                  {clears ? "✓ CLEARS" : "✗ BELOW"}
                                </Badge>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
