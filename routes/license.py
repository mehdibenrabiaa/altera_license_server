from fastapi import APIRouter, Depends, HTTPException, Header
from sqlmodel import Session, select
from datetime import date
from jose import jwt, JWTError
from pydantic import BaseModel
from typing import Optional
from database import get_session
from models import License, Activation
import os


router = APIRouter(prefix="/license", tags=["license"])

SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
ALGORITHM = "HS256"


# --- Admin guard ---
def verify_admin(x_admin_key: str = Header(...)):
    if x_admin_key != os.getenv("ADMIN_SECRET"):
        raise HTTPException(403, "Forbidden")


# --- Request schemas ---
class ActivateRequest(BaseModel):
    license_key: str
    machine_id: str
    username: Optional[str] = None  # Windows username sent by the client


class ValidateRequest(BaseModel):
    token: str
    machine_id: str


# --- Response schemas ---
class ValidateResponse(BaseModel):
    valid: bool
    plan: str
    email: str
    expired: bool = False
    expiry_date: Optional[str] = None
    message: Optional[str] = None
    license_key: Optional[str] = None


# --- Helpers ---
def make_token(license: License, machine_id: str) -> str:
    payload = {
        "sub": license.email,
        "key": license.key,
        "machine": machine_id,
        "plan": license.plan,
        "expiry": str(license.expiry),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


# --- Routes ---
@router.post("/activate")
def activate(req: ActivateRequest, session: Session = Depends(get_session)):
    # Look up the license
    lic = session.exec(select(License).where(License.key == req.license_key)).first()
    if not lic:
        raise HTTPException(404, "License not found")

    # Check expiry
    if lic.expiry < date.today():
        raise HTTPException(403, "License has expired")

    # Check if this machine is already activated (non-revoked)
    existing = session.exec(
        select(Activation).where(
            Activation.license_key == req.license_key,
            Activation.machine_id == req.machine_id,
            Activation.revoked == False,
        )
    ).first()

    if existing:
        # Already activated — update username if provided and return token
        if req.username:
            existing.username = req.username
            session.add(existing)
            session.commit()
        return {
            "token": make_token(lic, req.machine_id),
            "email": lic.email,
            "plan": lic.plan,
            "expiry_date": str(lic.expiry),
        }

    # Check seat count
    active_seats = session.exec(
        select(Activation).where(
            Activation.license_key == req.license_key,
            Activation.revoked == False,
        )
    ).all()

    if len(active_seats) >= lic.max_seats:
        raise HTTPException(403, f"Seat limit reached ({lic.max_seats} seats)")

    # Create new activation, storing the Windows username
    activation = Activation(
        license_key=req.license_key,
        machine_id=req.machine_id,
        username=req.username,  # <-- saved here
    )
    session.add(activation)
    session.commit()

    return {
        "token": make_token(lic, req.machine_id),
        "email": lic.email,
        "plan": lic.plan,
        "expiry_date": str(lic.expiry),
    }


@router.post("/validate", response_model=ValidateResponse)
def validate(req: ValidateRequest, session: Session = Depends(get_session)):
    try:
        payload = jwt.decode(req.token, SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return ValidateResponse(valid=False, plan="", email="", message="Invalid token")

    license_key = payload.get("key")
    machine_id = payload.get("machine")

    if machine_id != req.machine_id:
        return ValidateResponse(
            valid=False, plan="", email="", message="Machine ID mismatch"
        )

    lic = session.exec(select(License).where(License.key == license_key)).first()
    if not lic:
        return ValidateResponse(
            valid=False, plan="", email="", message="License not found"
        )

    activation = session.exec(
        select(Activation).where(
            Activation.license_key == license_key,
            Activation.machine_id == req.machine_id,
            Activation.revoked == False,
        )
    ).first()

    if not activation:
        return ValidateResponse(
            valid=False, plan="", email="", message="Activation revoked or not found"
        )

    expired = lic.expiry < date.today()
    return ValidateResponse(
        valid=not expired,
        plan=lic.plan,
        email=lic.email,
        expired=expired,
        expiry_date=str(lic.expiry),
        license_key=license_key,
    )


@router.post("/deactivate")
def deactivate(req: ActivateRequest, session: Session = Depends(get_session)):
    activation = session.exec(
        select(Activation).where(
            Activation.license_key == req.license_key,
            Activation.machine_id == req.machine_id,
            Activation.revoked == False,
        )
    ).first()

    if not activation:
        raise HTTPException(404, "Active activation not found")

    activation.revoked = True
    session.add(activation)
    session.commit()
    return {"ok": True, "message": "Deactivated successfully"}
