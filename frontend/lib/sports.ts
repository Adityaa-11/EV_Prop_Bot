export const SPORT_OPTIONS = [
  { value: "all", label: "All Sports" },
  { value: "mlb", label: "MLB" },
  { value: "nba", label: "NBA" },
  { value: "nfl", label: "NFL" },
  { value: "nhl", label: "NHL" },
  { value: "wnba", label: "WNBA" },
  { value: "ncaab", label: "NCAAB" },
  { value: "ncaaf", label: "NCAAF" },
  { value: "cfl", label: "CFL" },
  { value: "mls", label: "MLS" },
  { value: "epl", label: "EPL" },
  { value: "soccer", label: "Soccer" },
  { value: "summer", label: "NBA Summer" },
] as const

export const SPORT_FILTER_CODES = SPORT_OPTIONS.filter((s) => s.value !== "all").map(
  (s) => s.value,
)

export type SportCode = (typeof SPORT_OPTIONS)[number]["value"]
