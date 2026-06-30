// World markets for the Home globe. Each exchange carries its IANA timezone and
// local trading hours, so "open / closed right now" is *computed* from the user's
// clock — a real, free signal, not a fabricated feed. Index movement (% change)
// needs a price source we haven't wired, so we deliberately don't show it yet.
//
// `msci` is the MSCI market classification (Developed / Emerging / Frontier) — the
// taxonomy that powers the "trim EM / add a developing market" insight.

export type MarketStatus = "open" | "closed";
export type MsciTier = "DM" | "EM" | "FM";

export interface Exchange {
  id: string;
  name: string;
  short: string;
  city: string;
  country: string; // matches the `jurisdiction` strings on has_subsidiary edges
  flag: string;
  lat: number;
  lng: number;
  tz: string; // IANA timezone
  open: string; // local "HH:MM"
  close: string; // local "HH:MM"
  days: number[]; // trading days, 0=Sun .. 6=Sat
  msci: MsciTier;
}

const MF = [1, 2, 3, 4, 5]; // Mon–Fri

export const EXCHANGES: Exchange[] = [
  { id: "nyse", name: "New York Stock Exchange", short: "NYSE", city: "New York", country: "United States", flag: "🇺🇸", lat: 40.707, lng: -74.011, tz: "America/New_York", open: "09:30", close: "16:00", days: MF, msci: "DM" },
  { id: "tsx", name: "Toronto Stock Exchange", short: "TSX", city: "Toronto", country: "Canada", flag: "🇨🇦", lat: 43.648, lng: -79.382, tz: "America/Toronto", open: "09:30", close: "16:00", days: MF, msci: "DM" },
  { id: "b3", name: "B3", short: "B3", city: "São Paulo", country: "Brazil", flag: "🇧🇷", lat: -23.551, lng: -46.634, tz: "America/Sao_Paulo", open: "10:00", close: "17:00", days: MF, msci: "EM" },
  { id: "lse", name: "London Stock Exchange", short: "LSE", city: "London", country: "United Kingdom", flag: "🇬🇧", lat: 51.515, lng: -0.099, tz: "Europe/London", open: "08:00", close: "16:30", days: MF, msci: "DM" },
  { id: "euronext", name: "Euronext Paris", short: "ENX", city: "Paris", country: "France", flag: "🇫🇷", lat: 48.869, lng: 2.341, tz: "Europe/Paris", open: "09:00", close: "17:30", days: MF, msci: "DM" },
  { id: "xetra", name: "Deutsche Börse (Xetra)", short: "XETR", city: "Frankfurt", country: "Germany", flag: "🇩🇪", lat: 50.113, lng: 8.671, tz: "Europe/Berlin", open: "09:00", close: "17:30", days: MF, msci: "DM" },
  { id: "six", name: "SIX Swiss Exchange", short: "SIX", city: "Zurich", country: "Switzerland", flag: "🇨🇭", lat: 47.369, lng: 8.539, tz: "Europe/Zurich", open: "09:00", close: "17:30", days: MF, msci: "DM" },
  { id: "jse", name: "Johannesburg Stock Exchange", short: "JSE", city: "Johannesburg", country: "South Africa", flag: "🇿🇦", lat: -26.146, lng: 28.041, tz: "Africa/Johannesburg", open: "09:00", close: "17:00", days: MF, msci: "EM" },
  { id: "tadawul", name: "Saudi Exchange (Tadawul)", short: "TADAWUL", city: "Riyadh", country: "Saudi Arabia", flag: "🇸🇦", lat: 24.711, lng: 46.674, tz: "Asia/Riyadh", open: "10:00", close: "15:00", days: [0, 1, 2, 3, 4], msci: "EM" },
  { id: "nse", name: "National Stock Exchange of India", short: "NSE", city: "Mumbai", country: "India", flag: "🇮🇳", lat: 19.063, lng: 72.868, tz: "Asia/Kolkata", open: "09:15", close: "15:30", days: MF, msci: "EM" },
  { id: "sse", name: "Shanghai Stock Exchange", short: "SSE", city: "Shanghai", country: "China", flag: "🇨🇳", lat: 31.234, lng: 121.481, tz: "Asia/Shanghai", open: "09:30", close: "15:00", days: MF, msci: "EM" },
  { id: "hkex", name: "Hong Kong Exchanges", short: "HKEX", city: "Hong Kong", country: "Hong Kong", flag: "🇭🇰", lat: 22.283, lng: 114.159, tz: "Asia/Hong_Kong", open: "09:30", close: "16:00", days: MF, msci: "DM" },
  { id: "sgx", name: "Singapore Exchange", short: "SGX", city: "Singapore", country: "Singapore", flag: "🇸🇬", lat: 1.281, lng: 103.851, tz: "Asia/Singapore", open: "09:00", close: "17:00", days: MF, msci: "DM" },
  { id: "tse", name: "Tokyo Stock Exchange", short: "TSE", city: "Tokyo", country: "Japan", flag: "🇯🇵", lat: 35.681, lng: 139.767, tz: "Asia/Tokyo", open: "09:00", close: "15:00", days: MF, msci: "DM" },
  { id: "asx", name: "Australian Securities Exchange", short: "ASX", city: "Sydney", country: "Australia", flag: "🇦🇺", lat: -33.868, lng: 151.207, tz: "Australia/Sydney", open: "10:00", close: "16:00", days: MF, msci: "DM" },
];

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** Local wall-clock (minutes since midnight) and weekday in an exchange's timezone. */
function localNow(tz: string, now: Date): { minutes: number; weekday: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    hour12: false,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  let hour = parseInt(get("hour"), 10);
  if (hour === 24) hour = 0; // some runtimes render midnight as "24"
  return { minutes: hour * 60 + parseInt(get("minute"), 10), weekday: WEEKDAYS.indexOf(get("weekday")) };
}

const toMin = (hhmm: string): number => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};

/** Open / closed right now, by the exchange's own clock. (Holidays not modelled.) */
export function marketStatus(ex: Exchange, now: Date = new Date()): MarketStatus {
  const { minutes, weekday } = localNow(ex.tz, now);
  if (!ex.days.includes(weekday)) return "closed";
  return minutes >= toMin(ex.open) && minutes < toMin(ex.close) ? "open" : "closed";
}

/** "14:32" in the exchange's local time, for the panel. */
export function localTime(ex: Exchange, now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-US", { timeZone: ex.tz, hour12: false, hour: "2-digit", minute: "2-digit" }).format(now);
}

export const TIER_LABEL: Record<MsciTier, string> = {
  DM: "Developed market",
  EM: "Emerging market",
  FM: "Frontier market",
};
