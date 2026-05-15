const OVERLAY_BASE_URL = "http://localhost:9000/overlays";

export function buildOverlayUrl(overlayKey: string | null | undefined): string | null {
  if (!overlayKey) return null;
  return `${OVERLAY_BASE_URL}/${overlayKey.replace(/^\/+/, "")}`;
}
