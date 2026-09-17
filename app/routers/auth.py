from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import verify_password, create_token, current_user, admin_only, rate_limit, hash_password
from ..database import get_db
from ..models import User
from ..schemas import LoginIn, TokenOut, UserOut, UserIn, PasswordChange

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user or not verify_password(data.password, user.password_hash) or not user.is_active:
        raise HTTPException(401, "Invalid email or password")
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/change-password")
def change_password(data: PasswordChange, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is wrong")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"ok": True}


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(data: UserIn, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email.lower()).first():
        raise HTTPException(409, "Email already exists")
    u = User(email=data.email.lower(), name=data.name, password_hash=hash_password(data.password), role=data.role)
    db.add(u); db.commit(); db.refresh(u)
    return u


@router.patch("/users/{user_id}/toggle", response_model=UserOut)
def toggle_user(user_id: int, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "Cannot deactivate yourself")
    u.is_active = not u.is_active
    db.commit(); db.refresh(u)
    return u
