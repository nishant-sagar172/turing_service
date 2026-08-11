// Client API key — stored in sessionStorage (dies with the tab).
// Only used by the portal; never prefixed NEXT_PUBLIC_.

const KEY = "turing_api_key";

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(KEY);
}

export function setApiKey(key: string): void {
  sessionStorage.setItem(KEY, key);
}

export function clearApiKey(): void {
  sessionStorage.removeItem(KEY);
}
