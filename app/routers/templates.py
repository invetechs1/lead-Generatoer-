from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import current_user, admin_only
from ..database import get_db
from ..models import Template, User
from ..schemas import TemplateIn, TemplateOut

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.query(Template).order_by(Template.stage, Template.id).all()


@router.post("", response_model=TemplateOut, status_code=201)
def create(data: TemplateIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    t = Template(**data.model_dump()); db.add(t); db.commit(); db.refresh(t)
    return t


@router.put("/{tid}", response_model=TemplateOut)
def update(tid: int, data: TemplateIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    t = db.get(Template, tid)
    if not t:
        raise HTTPException(404, "Template not found")
    for k, v in data.model_dump().items():
        setattr(t, k, v)
    db.commit(); db.refresh(t)
    return t


@router.delete("/{tid}", status_code=204)
def delete(tid: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    t = db.get(Template, tid)
    if not t:
        raise HTTPException(404, "Template not found")
    db.delete(t); db.commit()
