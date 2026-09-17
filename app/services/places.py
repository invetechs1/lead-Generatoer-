"""Google Places API (New) — Text Search. Returns businesses; filters those without a website."""
import httpx

from ..config import settings

FIELDS = "places.id,places.photos,places.displayName,places.nationalPhoneNumber,places.internationalPhoneNumber,places.websiteUri,places.googleMapsUri,places.rating,places.userRatingCount,places.formattedAddress"


async def search(query: str, city: str, max_results: int = 20) -> list[dict]:
    if not settings.GOOGLE_PLACES_API_KEY:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set")
    out: list[dict] = []
    token = None
    async with httpx.AsyncClient(timeout=25) as client:
        while len(out) < max_results:
            body = {"textQuery": f"{query} {city}", "languageCode": "ar", "regionCode": "SA", "pageSize": 20}
            if token:
                body["pageToken"] = token
            r = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                json=body,
                headers={"X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY, "X-Goog-FieldMask": FIELDS + ",nextPageToken"},
            )
            r.raise_for_status()
            data = r.json()
            for p in data.get("places", []):
                out.append({
                    "place_id": p.get("id", ""),
                    "photo_names": [ph.get("name") for ph in (p.get("photos") or [])[:8] if ph.get("name")],
                    "name": (p.get("displayName") or {}).get("text", ""),
                    "phone": p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber") or "",
                    "website": p.get("websiteUri") or "",
                    "maps_url": p.get("googleMapsUri") or "",
                    "rating": p.get("rating"),
                    "reviews": p.get("userRatingCount"),
                    "address": p.get("formattedAddress", ""),
                })
            token = data.get("nextPageToken")
            if not token:
                break
    return out[:max_results]


async def photo_names(place_id: str = "", name: str = "", city: str = "") -> tuple[str, list[str]]:
    """Return (place_id, photo resource names). Uses Place Details when the id is known, else a text search."""
    if not settings.GOOGLE_PLACES_API_KEY:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set")
    headers = {"X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY}
    async with httpx.AsyncClient(timeout=25) as client:
        if place_id:
            r = await client.get(f"https://places.googleapis.com/v1/places/{place_id}", headers={**headers, "X-Goog-FieldMask": "id,photos"})
            r.raise_for_status()
            d = r.json()
            return d.get("id", place_id), [ph["name"] for ph in (d.get("photos") or [])[:8] if ph.get("name")]
        r = await client.post("https://places.googleapis.com/v1/places:searchText", json={"textQuery": f"{name} {city}", "languageCode": "ar", "regionCode": "SA", "pageSize": 1},
                              headers={**headers, "X-Goog-FieldMask": "places.id,places.photos"})
        r.raise_for_status()
        places_ = r.json().get("places") or []
        if not places_:
            return "", []
        p = places_[0]
        return p.get("id", ""), [ph["name"] for ph in (p.get("photos") or [])[:8] if ph.get("name")]


async def download_photos(names: list[str], dest_dir, max_width: int = 1600) -> list[str]:
    """Download Google place photos to dest_dir; returns the saved file names. Photos are the business's own Maps photos."""
    from pathlib import Path
    dest = Path(dest_dir); dest.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as client:
        for i, n in enumerate(names):
            try:
                r = await client.get(f"https://places.googleapis.com/v1/{n}/media", params={"maxWidthPx": max_width, "key": settings.GOOGLE_PLACES_API_KEY})
                r.raise_for_status()
                ext = ".png" if "png" in r.headers.get("content-type", "") else ".jpg"
                fn = f"google_{i+1}{ext}"
                (dest / fn).write_bytes(r.content)
                saved.append(fn)
            except Exception:
                continue
    return saved
