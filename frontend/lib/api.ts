/**
 * API Client for EV Dashboard
 * Connects frontend to the FastAPI backend
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

// Types matching the API responses
export interface ApiProp {
  id: string
  player_name: string
  team: string
  opponent: string | null
  sport: string
  stat_type: string
  platform: string
  line: number
  game_time: string | null
}

export interface SharpOdds {
  bookmaker: string
  line: number
  over_odds: number
  under_odds: number
  over_probability: number
  under_probability: number
  is_sharp: boolean
}

// Individual book odds for comparison table
export interface BookOdds {
  bookmaker: string
  line: number
  over_odds: number
  under_odds: number
}

export interface EVPlay {
  prop: ApiProp
  sharp_odds: SharpOdds | null
  all_book_odds?: BookOdds[]  // All sportsbook odds for comparison
  recommended_play: "OVER" | "UNDER"
  win_probability: number
  ev_percentage: number
  best_for: string[]
}

export interface Middle {
  player_name: string
  stat_type: string
  sport: string
  platform_a: {
    name: string
    line: number
    recommended: string
  }
  platform_b: {
    name: string
    line: number
    recommended: string
  }
  spread: number
  middle_zone: number[]
}

export interface PropsResponse {
  count: number
  sport: string
  props: ApiProp[]
}

export interface EVResponse {
  count: number
  sport: string
  sharp_books_used: string[]
  plays: EVPlay[]
}

export interface MiddlesResponse {
  count: number
  sport: string
  middles: Middle[]
}

export interface GamesResponse {
  sport: string
  teams_with_props: string[]
  total_props: number
  platforms: {
    prizepicks: number
    underdog: number
  }
}

export interface HealthResponse {
  status: string
  odds_api_configured: boolean
  sharp_books: string[]
  platforms: {
    prizepicks: boolean
    underdog: boolean
    chalkboard: boolean
    betr: boolean
  }
}

// API Functions
async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`
  
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    })
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`)
    }
    
    return response.json()
  } catch (error) {
    console.error(`API request failed: ${endpoint}`, error)
    throw error
  }
}

// Health check
export async function checkHealth(): Promise<HealthResponse> {
  return fetchApi<HealthResponse>("/api/health")
}

// Odds API usage
export interface OddsUsageResponse {
  configured: boolean
  requests_used?: number
  requests_remaining?: number
  requests_total?: number
  error?: string
  auto_rotation?: {
    enabled: boolean
    total_keys: number
    current_key: number
  }
}

export async function getOddsUsage(): Promise<OddsUsageResponse> {
  return fetchApi<OddsUsageResponse>("/api/odds-usage")
}

// All keys usage
export interface KeyUsage {
  key_number: number
  key_preview: string
  status: "active" | "depleted" | "invalid" | "error"
  requests_used: number
  requests_remaining: number
  error?: string
}

export interface AllKeysUsageResponse {
  current_key: number
  total_keys: number
  keys: KeyUsage[]
  total_remaining: number
}

export async function getAllKeysUsage(): Promise<AllKeysUsageResponse> {
  return fetchApi<AllKeysUsageResponse>("/api/all-keys-usage")
}

// Rotate key
export interface RotateKeyResponse {
  success: boolean
  previous_key?: number
  current_key: number
  total_keys: number
  message?: string
}

export async function rotateKey(): Promise<RotateKeyResponse> {
  return fetchApi<RotateKeyResponse>("/api/rotate-key", { method: "POST" })
}

// Set specific key
export async function setKey(keyIndex: number): Promise<RotateKeyResponse> {
  return fetchApi<RotateKeyResponse>(`/api/set-key/${keyIndex}`, { method: "POST" })
}

// Get all props
export async function getProps(params: {
  sport?: string
  platform?: string
  stat?: string
  player?: string
  refresh?: boolean
}): Promise<PropsResponse> {
  const searchParams = new URLSearchParams()
  if (params.sport) searchParams.set("sport", params.sport)
  if (params.platform) searchParams.set("platform", params.platform)
  if (params.stat) searchParams.set("stat", params.stat)
  if (params.player) searchParams.set("player", params.player)
  if (params.refresh) searchParams.set("refresh", "true")
  
  const query = searchParams.toString()
  return fetchApi<PropsResponse>(`/api/props${query ? `?${query}` : ""}`)
}

// Get +EV plays
export async function getEVPlays(params: {
  sport?: string
  platform?: string
  minEv?: number
  minWin?: number
  refresh?: boolean
}): Promise<EVResponse> {
  const searchParams = new URLSearchParams()
  if (params.sport) searchParams.set("sport", params.sport)
  if (params.platform) searchParams.set("platform", params.platform)
  if (params.minEv !== undefined) searchParams.set("min_ev", params.minEv.toString())
  if (params.minWin !== undefined) searchParams.set("min_win", params.minWin.toString())
  if (params.refresh) searchParams.set("refresh", "true")
  
  const query = searchParams.toString()
  return fetchApi<EVResponse>(`/api/ev${query ? `?${query}` : ""}`)
}

// Get middle opportunities
export async function getMiddles(params: {
  sport?: string
  minSpread?: number
  refresh?: boolean
}): Promise<MiddlesResponse> {
  const searchParams = new URLSearchParams()
  if (params.sport) searchParams.set("sport", params.sport)
  if (params.minSpread !== undefined) searchParams.set("min_spread", params.minSpread.toString())
  if (params.refresh) searchParams.set("refresh", "true")
  
  const query = searchParams.toString()
  return fetchApi<MiddlesResponse>(`/api/middles${query ? `?${query}` : ""}`)
}

// Compare player across platforms
export async function comparePlayer(playerName: string, sport: string = "nba") {
  return fetchApi(`/api/compare/${encodeURIComponent(playerName)}?sport=${sport}`)
}

// Get games summary
export async function getGames(sport: string = "all", refresh: boolean = false): Promise<GamesResponse> {
  const searchParams = new URLSearchParams()
  if (sport && sport !== "all") searchParams.set("sport", sport)
  if (refresh) searchParams.set("refresh", "true")
  const query = searchParams.toString()
  return fetchApi<GamesResponse>(`/api/games${query ? `?${query}` : ""}`)
}

// Calculate no-vig odds
export async function calculateEV(overOdds: number, underOdds: number) {
  return fetchApi(`/api/calc?over_odds=${overOdds}&under_odds=${underOdds}`, {
    method: "POST",
  })
}

