from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session, select
from database import init_db, get_session
from routes.license import router as license_router, verify_admin
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional
from models import License, Activation
from datetime import date
from fastapi.middleware.cors import CORSMiddleware


load_dotenv()

app = FastAPI(title="Altera License Server")
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(license_router)


# --- Schemas ---
class CreateLicensePayload(BaseModel):
    key: str
    email: str
    plan: str
    expiry: str
    max_seats: int = 1


class UpdateLicensePayload(BaseModel):
    email: Optional[str] = None
    plan: Optional[str] = None
    expiry: Optional[str] = None
    max_seats: Optional[int] = None


# --- Admin: Create License ---
@app.post("/admin/create-license")
def create_license(
    payload: CreateLicensePayload,
    _=Depends(verify_admin),
    session: Session = Depends(get_session),
):

    existing = session.exec(select(License).where(License.key == payload.key)).first()
    if existing:
        raise HTTPException(400, "A license with this key already exists")

    lic = License(
        key=payload.key,
        email=payload.email,
        plan=payload.plan,
        expiry=date.fromisoformat(payload.expiry),
        max_seats=payload.max_seats,
    )
    session.add(lic)
    session.commit()
    return {"ok": True}


# --- Admin: Update License ---
@app.patch("/admin/licenses/{license_key}")
def update_license(
    license_key: str,
    payload: UpdateLicensePayload,
    _=Depends(verify_admin),
    session: Session = Depends(get_session),
):
    lic = session.exec(select(License).where(License.key == license_key)).first()
    if not lic:
        raise HTTPException(404, "License not found")

    if payload.email is not None:
        lic.email = payload.email
    if payload.plan is not None:
        lic.plan = payload.plan
    if payload.expiry is not None:
        lic.expiry = date.fromisoformat(payload.expiry)
    if payload.max_seats is not None:
        lic.max_seats = payload.max_seats

    session.add(lic)
    session.commit()
    session.refresh(lic)
    return {
        "ok": True,
        "updated": {
            "key": lic.key,
            "email": lic.email,
            "plan": lic.plan,
            "expiry": str(lic.expiry),
            "max_seats": lic.max_seats,
        },
    }


# --- Admin: Delete License ---
@app.delete("/admin/licenses/{license_key}")
def delete_license(
    license_key: str, _=Depends(verify_admin), session: Session = Depends(get_session)
):
    lic = session.exec(select(License).where(License.key == license_key)).first()
    if not lic:
        raise HTTPException(404, "License not found")

    # Also delete all associated activations
    activations = session.exec(
        select(Activation).where(Activation.license_key == license_key)
    ).all()
    for act in activations:
        session.delete(act)

    session.delete(lic)
    session.commit()
    return {
        "ok": True,
        "message": f"License {license_key} and all its activations deleted",
    }


# --- Admin: View Licenses Table ---
@app.get("/admin/licenses")
def list_licenses(_=Depends(verify_admin), session: Session = Depends(get_session)):
    licenses = session.exec(select(License)).all()
    return {
        "count": len(licenses),
        "licenses": [
            {
                "id": lic.id,
                "key": lic.key,
                "email": lic.email,
                "plan": lic.plan,
                "expiry": str(lic.expiry),
                "max_seats": lic.max_seats,
            }
            for lic in licenses
        ],
    }


# --- Admin: View Activations Table ---
@app.get("/admin/activations")
def list_activations(_=Depends(verify_admin), session: Session = Depends(get_session)):
    activations = session.exec(select(Activation)).all()
    return {
        "count": len(activations),
        "activations": [
            {
                "id": act.id,
                "license_key": act.license_key,
                "machine_id": act.machine_id,
                "activated_at": str(act.activated_at),
                "revoked": act.revoked,
            }
            for act in activations
        ],
    }


# --- Admin: Full Overview (both tables joined) ---
@app.get("/admin/overview")
def overview(_=Depends(verify_admin), session: Session = Depends(get_session)):
    licenses = session.exec(select(License)).all()
    activations = session.exec(select(Activation)).all()

    result = []
    for lic in licenses:
        lic_activations = [a for a in activations if a.license_key == lic.key]
        active = [a for a in lic_activations if not a.revoked]
        result.append(
            {
                "key": lic.key,
                "email": lic.email,
                 "username": lic.username,
                "plan": lic.plan,
                "expiry": str(lic.expiry),
                "max_seats": lic.max_seats,
                "seats_used": len(active),
                "seats_available": lic.max_seats - len(active),
                "activations": [
                    {
                        "machine_id": a.machine_id,"username": a.username,
                        "activated_at": str(a.activated_at),
                        "revoked": a.revoked,
                    }
                    for a in lic_activations
                ],
            }
        )

    return {
        "total_licenses": len(licenses),
        "total_activations": len(activations),
        "licenses": result,
    }


