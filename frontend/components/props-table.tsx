"use client"

import * as React from "react"
import { ChevronUp, ChevronDown, ArrowUpRight, ArrowDownRight } from "lucide-react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { Prop } from "@/lib/types"
import { cn } from "@/lib/utils"
import { PropDetailDialog } from "@/components/prop-detail-dialog"

interface PropsTableProps {
  props: Prop[]
}

export function PropsTable({ props }: PropsTableProps) {
  const [sortKey, setSortKey] = React.useState<string | null>(null)
  const [sortDirection, setSortDirection] = React.useState<"asc" | "desc">("desc")
  const [selectedProp, setSelectedProp] = React.useState<Prop | null>(null)
  const [currentPage, setCurrentPage] = React.useState(1)
  const itemsPerPage = 50

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc")
    } else {
      setSortKey(key)
      setSortDirection("desc")
    }
  }

  const getEVColor = (evPercentage?: number) => {
    if (!evPercentage) return ""
    if (evPercentage >= 5) return "bg-primary/20 hover:bg-primary/30"
    if (evPercentage >= 2) return "bg-accent/20 hover:bg-accent/30"
    return ""
  }

  const getBestPlayIndicator = (prop: Prop) => {
    if (!prop.bestPlay) return { text: "--", icon: null }

    const platformShort = {
      PrizePicks: "PP",
      Underdog: "UD",
      Sleeper: "SLP",
      Betr: "BTR",
    }[prop.bestPlay.platform]

    const icon =
      prop.bestPlay.play === "OVER" ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />

    return {
      text: platformShort,
      icon,
      play: prop.bestPlay.play,
    }
  }

  const totalPages = Math.ceil(props.length / itemsPerPage)
  const startIndex = (currentPage - 1) * itemsPerPage
  const endIndex = startIndex + itemsPerPage
  const currentProps = props.slice(startIndex, endIndex)

  return (
    <>
      <div className="rounded-lg border border-border bg-card">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="font-semibold">
                  <button
                    onClick={() => handleSort("player")}
                    className="flex items-center gap-1 hover:text-foreground"
                  >
                    Player
                    {sortKey === "player" &&
                      (sortDirection === "asc" ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      ))}
                  </button>
                </TableHead>
                <TableHead className="font-semibold">
                  <button onClick={() => handleSort("game")} className="flex items-center gap-1 hover:text-foreground">
                    Game
                    {sortKey === "game" &&
                      (sortDirection === "asc" ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      ))}
                  </button>
                </TableHead>
                <TableHead className="font-semibold">
                  <button onClick={() => handleSort("stat")} className="flex items-center gap-1 hover:text-foreground">
                    Stat
                    {sortKey === "stat" &&
                      (sortDirection === "asc" ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      ))}
                  </button>
                </TableHead>
                <TableHead className="text-center font-semibold font-mono">PP</TableHead>
                <TableHead className="text-center font-semibold font-mono">UD</TableHead>
                <TableHead className="text-center font-semibold font-mono">SLP</TableHead>
                <TableHead className="text-center font-semibold font-mono">BETR</TableHead>
                <TableHead className="text-center font-semibold">Best</TableHead>
                <TableHead className="text-right font-semibold">
                  <button
                    onClick={() => handleSort("winrate")}
                    className="flex items-center gap-1 hover:text-foreground ml-auto"
                  >
                    Win%
                    {sortKey === "winrate" &&
                      (sortDirection === "asc" ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      ))}
                  </button>
                </TableHead>
                <TableHead className="text-right font-semibold">
                  <button
                    onClick={() => handleSort("ev")}
                    className="flex items-center gap-1 hover:text-foreground ml-auto"
                  >
                    EV%
                    {sortKey === "ev" &&
                      (sortDirection === "asc" ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      ))}
                  </button>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {currentProps.map((prop) => {
                const bestPlay = getBestPlayIndicator(prop)
                const evColor = getEVColor(prop.bestPlay?.evPercentage)

                return (
                  <TableRow
                    key={prop.id}
                    className={cn("cursor-pointer transition-colors", evColor, !prop.bestPlay && "opacity-60")}
                    onClick={() => setSelectedProp(prop)}
                  >
                    <TableCell className="font-medium">
                      <div>
                        <div>{prop.playerName}</div>
                        <div className="text-xs text-muted-foreground">{prop.teamAbbr}</div>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{prop.game}</TableCell>
                    <TableCell className="text-sm">{prop.stat}</TableCell>
                    <TableCell className="text-center font-mono text-sm">{prop.lines.prizepicks ?? "--"}</TableCell>
                    <TableCell className="text-center font-mono text-sm">{prop.lines.underdog ?? "--"}</TableCell>
                    <TableCell className="text-center font-mono text-sm">{prop.lines.sleeper ?? "--"}</TableCell>
                    <TableCell className="text-center font-mono text-sm">{prop.lines.betr ?? "--"}</TableCell>
                    <TableCell className="text-center">
                      {bestPlay.text !== "--" ? (
                        <Badge
                          variant="outline"
                          className={cn(
                            "gap-1 font-mono text-xs",
                            bestPlay.play === "OVER"
                              ? "text-primary border-primary"
                              : "text-secondary border-secondary",
                          )}
                        >
                          {bestPlay.text}
                          {bestPlay.icon}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">--</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {prop.bestPlay ? (
                        <span className={cn(prop.bestPlay.evPercentage > 0 && "text-primary font-semibold")}>
                          {prop.bestPlay.winProbability.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-muted-foreground">--</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {prop.bestPlay ? (
                        <span
                          className={cn(
                            "font-semibold",
                            prop.bestPlay.evPercentage >= 5 && "text-primary",
                            prop.bestPlay.evPercentage >= 2 && prop.bestPlay.evPercentage < 5 && "text-accent",
                          )}
                        >
                          {prop.bestPlay.evPercentage > 0 ? "+" : ""}
                          {prop.bestPlay.evPercentage.toFixed(1)}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">--</span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between border-t border-border px-6 py-4">
          <p className="text-sm text-muted-foreground">
            Showing {startIndex + 1}-{Math.min(endIndex, props.length)} of {props.length}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              ← Prev
            </Button>
            <span className="text-sm">
              Page {currentPage} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
            >
              Next →
            </Button>
          </div>
        </div>
      </div>

      {/* Prop Detail Dialog */}
      {selectedProp && (
        <PropDetailDialog
          prop={selectedProp}
          open={!!selectedProp}
          onOpenChange={(open) => !open && setSelectedProp(null)}
        />
      )}
    </>
  )
}
