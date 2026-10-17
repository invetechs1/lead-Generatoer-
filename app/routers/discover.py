from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import Lead, User
from ..schemas import DiscoverIn, DiscoverItem, normalize_phone
from ..services import places

router = APIRouter(prefix="/api/discover", tags=["discover"])


@router.post("", response_model=list[DiscoverItem])
async def discover(data: DiscoverIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        raw = await places.search(data.query, data.city, data.max_results)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # network / quota
        raise HTTPException(502, f"Google Places error: {e}") from e
    existing = {p for (p,) in db.query(Lead.phone)}
    out = []
    for r in raw:
        if data.only_without_website and r["website"]:
            continue
        try:
            phone = normalize_phone(r["phone"])
        except ValueError:
            continue
        item = DiscoverItem(name=r["name"], phone=phone, city=data.city, website=r["website"], maps_url=r["maps_url"], rating=r["rating"], reviews=r["reviews"], already_exists=phone in existing)
        out.append(item)
        if data.save and not item.already_exists:
            db.add(Lead(name=item.name, phone=phone, city=data.city, sector=data.query, website=item.website, maps_url=item.maps_url, rating=item.rating, reviews=item.reviews, source="places", owner_id=user.id))
            existing.add(phone)
    if data.save:
        db.commit()
    return out
