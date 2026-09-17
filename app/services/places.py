"""Google Places API (New) — Text Search. Returns businesses; filters those without a website."""
import httpx

from ..config import settings

FIELDS = "places.displayName,places.nationalPhoneNumber,places.internationalPhoneNumber,places.websiteUri,places.googleMapsUri,places.rating,places.userRatingCount,places.formattedAddress"


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
