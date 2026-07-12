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
  event_id?: string | null
  market_key?: string | null
  is_alternate?: boolean
  captured_at?: string
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
  used_in_consensus?: boolean
}

export interface EVPlay {
  candidate_id?: string
  prop: ApiProp
  sharp_odds: SharpOdds | null
  all_book_odds?: BookOdds[]  // All sportsbook odds for comparison
  consensus?: {
    method: string
    book_count: number
    dispersion: number
    confidence: "low" | "medium" | "high"
    fair_odds: number
  }
  recommended_play: "OVER" | "UNDER"
  win_probability: number
  ev_percentage: number
  probability_edge?: number
  ev_method?: string
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

export interface PaperLeg {
  candidate_id: string
  player_name: string
  stat_type: string
  side: "OVER" | "UNDER"
  line: number
  game_time: string | null
  win_probability: number
  book_count: number
  entry_line: number
  closing_line: number | null
  line_clv: number | null
  closing_probability?: number | null
  probability_clv?: number | null
}

export interface PaperEntry {
  id: string
  platform: "prizepicks" | "underdog"
  sport: string
  status: "open" | "settled"
  execution_mode: "paper"
  tier: "excellent" | "strong"
  stake: number
  expected_roi: number
  potential_payout: number
  lock_time: string | null
  created_at: string
  settled_at: string | null
  result: "win" | "loss" | "push" | "void" | null
  payout: number | null
  profit: number | null
  delivery_status: string
  delivery_attempts?: number
  delivery_error?: string | null
  legs: PaperLeg[]
}

export interface PaperResponse {
  mode: "paper"
  summary: {
    starting_bankroll: number
    bankroll: number
    profit: number
    exposure: number
    entries: number
    open_entries: number
    wins: number
    losses: number
    pushes: number
    win_rate: number
    daily_staked: number
    daily_profit?: number
    last_updated: string | null
  }
  entries: PaperEntry[]
  automation: {
    status: string
    sport?: string
    message?: string | null
    candidate_count?: number
    watch_count?: number
    created_count?: number
    checked_at?: string
  }
  scheduler?: {
    enabled?: boolean
    running?: boolean
    status?: string
    checked_at?: string
    message?: string
    created_count?: number
  }
  quota?: {
    scans_today: number
    scan_cap: number
    remaining_scans: number
  }
  delivery_failures?: number
  settlement_backlog?: number
  updated_at: string
}

export interface LineObservation {
  candidate_id: string
  platform: string
  sport: string
  event_id: string | null
  player_name: string
  market_key: string
  side: string
  line: number
  win_probability: number
  book_count: number
  dispersion: number
  game_time: string | null
  observed_at: string
}

export interface LineHistoryResponse {
  count: number
  observations: LineObservation[]
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

export async function getPaperDashboard(): Promise<PaperResponse> {
  return fetchApi<PaperResponse>("/api/paper")
}

export async function getLineHistory(params: {
  sport?: string
  platform?: string
  player?: string
  limit?: number
} = {}): Promise<LineHistoryResponse> {
  const searchParams = new URLSearchParams()
  if (params.sport) searchParams.set("sport", params.sport)
  if (params.platform) searchParams.set("platform", params.platform)
  if (params.player) searchParams.set("player", params.player)
  if (params.limit) searchParams.set("limit", params.limit.toString())
  const query = searchParams.toString()
  return fetchApi<LineHistoryResponse>(`/api/paper/line-history${query ? `?${query}` : ""}`)
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
  minBooks?: number
  refresh?: boolean
}): Promise<EVResponse> {
  const searchParams = new URLSearchParams()
  if (params.sport) searchParams.set("sport", params.sport)
  if (params.platform) searchParams.set("platform", params.platform)
  if (params.minEv !== undefined) searchParams.set("min_ev", params.minEv.toString())
  if (params.minWin !== undefined) searchParams.set("min_win", params.minWin.toString())
  if (params.minBooks !== undefined) searchParams.set("min_books", params.minBooks.toString())
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

