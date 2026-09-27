"""Named groups of approved scopes and private configuration export."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from netsentinel.alerts import add_event
from netsentinel.auth import Csrf, CurrentSession, Db, error
from netsentinel.models import NetworkProfile, NetworkScope, utcnow
from netsentinel.timeutil import iso_utc

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


def default_profile(db: DBSession) -> NetworkProfile:
    profile = db.get(NetworkProfile, 1)
    if profile is None:
        profile = NetworkProfile(id=1, name="Default", description="Existing approved ranges")
        db.add(profile)
        db.flush()
    return profile


def profile_out(db: DBSession, profile: NetworkProfile) -> dict:
    count = len(
        db.scalars(select(NetworkScope.id).where(NetworkScope.profile_id == profile.id)).all()
    )
    return {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "created_at": iso_utc(profile.created_at),
        "scope_count": count,
    }


@router.get("")
def list_profiles(db: Db, _user: CurrentSession) -> list[dict]:
    default_profile(db)
    db.commit()
    return [
        profile_out(db, row)
        for row in db.scalars(select(NetworkProfile).order_by(NetworkProfile.id))
    ]


@router.post("", status_code=201)
def create_profile(payload: ProfileCreate, db: Db, user: CurrentSession, _csrf: Csrf) -> dict:
    name = payload.name.strip()
    if not name:
        error("invalid_name", "Profile name cannot be blank")
    default_profile(db)
    profile = NetworkProfile(
        name=name, description=payload.description.strip(), created_at=utcnow()
    )
    db.add(profile)
    try:
        db.flush()
        add_event(db, "profile_created", f"Created profile {name}", actor=user.user.username)
        db.commit()
    except IntegrityError:
        db.rollback()
        error("duplicate_profile", "A profile with this name already exists", 409)
    return profile_out(db, profile)


@router.patch("/{profile_id}")
def update_profile(
    profile_id: int, payload: ProfilePatch, db: Db, user: CurrentSession, _csrf: Csrf
) -> dict:
    profile = db.get(NetworkProfile, profile_id)
    if profile is None:
        error("not_found", "Profile not found", 404)
    if payload.name is not None:
        profile.name = payload.name.strip() or error("invalid_name", "Profile name cannot be blank")
    if payload.description is not None:
        profile.description = payload.description.strip()
    try:
        add_event(db, "profile_updated", f"Updated profile #{profile.id}", actor=user.user.username)
        db.commit()
    except IntegrityError:
        db.rollback()
        error("duplicate_profile", "A profile with this name already exists", 409)
    return profile_out(db, profile)


@router.get("/{profile_id}/export")
def export_profile(profile_id: int, db: Db, _user: CurrentSession) -> dict:
    """Return an authenticated, import-ready plan without approval or account secrets."""
    profile = db.get(NetworkProfile, profile_id)
    if profile is None:
        error("not_found", "Profile not found", 404)
    scopes = db.scalars(
        select(NetworkScope).where(NetworkScope.profile_id == profile_id).order_by(NetworkScope.id)
    )
    return {
        "format": "netsentinel-profile-v1",
        "name": profile.name,
        "description": profile.description,
        "requires_approval": True,
        "scopes": [
            {
                "name": scope.name,
                "cidr": scope.cidr,
                "ports": [int(port) for port in scope.ports.split(",")],
                "max_concurrency": scope.max_concurrency,
                "connect_timeout_ms": scope.connect_timeout_ms,
            }
            for scope in scopes
        ],
    }
