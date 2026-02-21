from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import date


class License(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    email: str
    plan: str  # "Professional", "Starter", etc.
    expiry: date
    max_seats: int = Field(default=1)


class Activation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    license_key: str = Field(foreign_key="license.key", index=True)
    machine_id: str
    username: Optional[str] = Field(default=None)  # New field for storing username
    activated_at: date = Field(default_factory=date.today)
    revoked: bool = Field(default=False)
