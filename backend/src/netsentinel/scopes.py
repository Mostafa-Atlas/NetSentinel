from ipaddress import IPv4Network, ip_network

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from netsentinel.alerts import add_event
from netsentinel.auth import Csrf, CurrentSession, Db, error
from netsentinel.models import NetworkProfile, NetworkScope, ScanRun, utcnow
from netsentinel.profiles import default_profile
from netsentinel.timeutil import iso_utc

router = APIRouter(prefix="/api/v1/scopes", tags=["scopes"])


def validate_cidr(value: str) -> str:
    try:
        network = ip_network(value, strict=True)
    except ValueError:
        raise ValueError("Enter a canonical private IPv4 CIDR such as 192.168.1.0/24") from None
    if (
        not isinstance(network, IPv4Network)
        or not network.is_private
        or network.is_loopback
        or network.is_link_local
        or network.is_multicast
        or network.is_reserved
    ):
        raise ValueError("Only private IPv4 LAN ranges are allowed")
    if (
        not network.subnet_of(IPv4Network("10.0.0.0/8"))
        and not network.subnet_of(IPv4Network("172.16.0.0/12"))
        and not network.subnet_of(IPv4Network("192.168.0.0/16"))
    ):
        raise ValueError("Only RFC 1918 private IPv4 ranges are allowed")
    if network.num_addresses > 256:
        raise ValueError("A scope may contain no more than 256 addresses")
    return str(network)


class ScopeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    cidr: str
    profile_id: int | None = Field(default=None, gt=0)
    approved: bool
    max_concurrency: int = Field(default=32, ge=1, le=32)
    connect_timeout_ms: int = Field(default=1000, ge=100, le=1000)
    ports: list[int] = Field(default_factory=lambda: [22, 80, 443], min_length=1, max_length=16)

    @field_validator("cidr")
    @classmethod
    def valid_cidr(cls, value: str) -> str:
        return validate_cidr(value)

    @field_validator("ports")
    @classmethod
    def valid_ports(cls, value: list[int]) -> list[int]:
        if any(port < 1 or port > 65535 for port in value) or len(set(value)) != len(value):
            raise ValueError("Ports must be unique integers from 1 to 65535")
        return value


class ScopeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    profile_id: int | None = Field(default=None, gt=0)
    enabled: bool | None = None
    approved: bool = False
    max_concurrency: int | None = Field(default=None, ge=1, le=32)
    connect_timeout_ms: int | None = Field(default=None, ge=100, le=1000)
    ports: list[int] | None = Field(default=None, min_length=1, max_length=16)

    @field_validator("ports")
    @classmethod
    def valid_ports(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and (
            any(port < 1 or port > 65535 for port in value) or len(set(value)) != len(value)
        ):
            raise ValueError("Ports must be unique integers from 1 to 65535")
        return value


class ScopeOut(BaseModel):
    id: int
    profile_id: int | None
    name: str
    cidr: str
    enabled: bool
    approved_at: str
    max_concurrency: int
    connect_timeout_ms: int
    ports: list[int]


def scope_out(scope: NetworkScope) -> ScopeOut:
    return ScopeOut(
        id=scope.id,
        profile_id=scope.profile_id,
        name=scope.name,
        cidr=scope.cidr,
        enabled=scope.enabled,
        approved_at=iso_utc(scope.approved_at) or "",
        max_concurrency=scope.max_concurrency,
        connect_timeout_ms=scope.connect_timeout_ms,
        ports=[int(p) for p in scope.ports.split(",")],
    )


@router.get("")
def list_scopes(db: Db, _user: CurrentSession) -> list[ScopeOut]:
    return [
        scope_out(scope) for scope in db.scalars(select(NetworkScope).order_by(NetworkScope.id))
    ]


@router.post("", status_code=201)
def create_scope(payload: ScopeCreate, db: Db, _user: CurrentSession, _csrf: Csrf) -> ScopeOut:
    if not payload.approved:
        error("approval_required", "Confirm that you are authorized to scan this range")
    profile = (
        db.get(NetworkProfile, payload.profile_id) if payload.profile_id else default_profile(db)
    )
    if profile is None:
        error("not_found", "Profile not found", 404)
    scope = NetworkScope(
        profile_id=profile.id,
        name=payload.name,
        cidr=payload.cidr,
        enabled=True,
        approved_at=utcnow(),
        max_concurrency=payload.max_concurrency,
        connect_timeout_ms=payload.connect_timeout_ms,
        ports=",".join(str(p) for p in payload.ports),
    )
    db.add(scope)
    try:
        db.flush()
        add_event(db, "scope_approved", f"Approved range {scope.cidr}", actor=_user.user.username)
        db.commit()
    except IntegrityError:
        db.rollback()
        error("duplicate_scope", "This range is already configured", 409)
    db.refresh(scope)
    return scope_out(scope)


@router.patch("/{scope_id}")
def update_scope(
    scope_id: int, payload: ScopeUpdate, db: Db, _user: CurrentSession, _csrf: Csrf
) -> ScopeOut:
    scope = db.get(NetworkScope, scope_id)
    if scope is None:
        error("not_found", "Scope not found", 404)
    if payload.name is not None:
        scope.name = payload.name
    if payload.profile_id is not None:
        if db.get(NetworkProfile, payload.profile_id) is None:
            error("not_found", "Profile not found", 404)
        if payload.profile_id != scope.profile_id:
            if db.scalar(select(ScanRun.id).where(ScanRun.scope_id == scope.id).limit(1)):
                error("profile_locked", "A scanned range cannot be moved between profiles", 409)
            scope.profile_id = payload.profile_id
    if payload.enabled is True and not scope.enabled:
        if not payload.approved:
            error("approval_required", "Confirm that you are authorized to scan this range")
        scope.approved_at = utcnow()
    policy_changed = (
        (
            payload.ports is not None
            and payload.ports != [int(port) for port in scope.ports.split(",")]
        )
        or (
            payload.max_concurrency is not None and payload.max_concurrency != scope.max_concurrency
        )
        or (
            payload.connect_timeout_ms is not None
            and payload.connect_timeout_ms != scope.connect_timeout_ms
        )
    )
    if policy_changed and not payload.approved:
        error("approval_required", "Confirm the updated probe policy for this range")
    if payload.ports is not None:
        scope.ports = ",".join(str(port) for port in payload.ports)
    if payload.max_concurrency is not None:
        scope.max_concurrency = payload.max_concurrency
    if payload.connect_timeout_ms is not None:
        scope.connect_timeout_ms = payload.connect_timeout_ms
    if payload.enabled is not None:
        scope.enabled = payload.enabled
    add_event(db, "scope_updated", f"Updated range {scope.cidr}", actor=_user.user.username)
    db.commit()
    return scope_out(scope)
