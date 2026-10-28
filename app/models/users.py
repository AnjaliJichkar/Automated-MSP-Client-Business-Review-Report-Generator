# app/models/users.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.core.database.engine import Base


class Account(Base):
    __tablename__ = "accounts"

    id           = Column(Integer, primary_key=True)
    account_name = Column(String, nullable=False)
    subdomain    = Column(String, unique=True)
    status       = Column(String, default="Active")
    created_at   = Column(DateTime)
    updated_at   = Column(DateTime)


class PlatformUser(Base):
    __tablename__ = "platform_users"

    id           = Column(Integer, primary_key=True)
    account_id   = Column(Integer)
    email        = Column(String)
    full_name    = Column(String)
    role         = Column(String, nullable=False)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime)
    last_login   = Column(DateTime)
    # UUID FK to auth.users (Supabase internal schema — FK not declared here)
    auth_user_id = Column(UUID(as_uuid=True), unique=True)
