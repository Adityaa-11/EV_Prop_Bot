export type Sport = "NBA" | "NFL" | "NHL" | "MLB" | "NCAAB" | "NCAAF"
export type Platform = "PrizePicks" | "Underdog" | "Sleeper" | "Betr"
export type Play = "OVER" | "UNDER"
export type StatType = "Points" | "Rebounds" | "Assists" | "3-Ptrs" | "Blocks" | "Steals" | "Turnovers"

export interface Team {
  name: string
  abbreviation: string
  logo?: string
}

export interface Game {
  id: string
  sport: Sport
  homeTeam: Team
  awayTeam: Team
  startTime: string // ISO datetime
  venue?: string
  tvChannel?: string
  propCount: number
  evPlayCount: number
  topEvPlay?: {
    playerName: string
    stat: string
    line: number
    play: Play
    winProbability: number
    evPercentage: number
  }
}

export interface PropLine {
  platform: Platform
  line: number | null
  isAvailable: boolean
}

export interface SharpOdds {
  book: string
  line: number
  overOdds: number // American odds
  underOdds: number
  overImplied: number // percentage
  underImplied: number
  noVigOverProb: number
  noVigUnderProb: number
}

export interface Prop {
  id: string
  playerName: string
  teamAbbr: string
  opponentAbbr: string
  game: string
  gameTime: string
  sport: Sport
  stat: StatType
  lines: {
    prizepicks: number | null
    underdog: number | null
    sleeper: number | null
    betr: number | null
  }
  bestPlay?: {
    platform: Platform
    play: Play
    line: number
    winProbability: number
    evPercentage: number
  }
  sharpOdds?: SharpOdds
}

export interface BreakEvenRates {
  flex5or6: number
  power4: number
  power2: number
}

export interface MiddleOpportunity {
  id: string
  playerName: string
  statType: string
  gameInfo: string
  gameTime: string
  platformA: {
    name: string
    line: number
    recommendedPlay: Play
  }
  platformB: {
    name: string
    line: number
    recommendedPlay: Play
  }
  middleZone: number[]
  spreadSize: number
}

export interface LineMovement {
  id: string
  playerName: string
  statType: string
  gameInfo: string
  gameTime: string
  minutesAgo: number
  movements: {
    platform: string
    oldLine: number
    newLine: number
    change: number
  }[]
  analysis: string
}
