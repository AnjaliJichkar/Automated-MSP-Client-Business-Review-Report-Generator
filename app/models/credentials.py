# app/models/credentials.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database.engine import Base


class M365Credential(Base):
    __tablename__ = "m365_credentials"

    id                 = Column(Integer, primary_key=True)
    organization_id    = Column(Integer, ForeignKey("organizations.id"), unique=True)
    account_id         = Column(Integer, ForeignKey("accounts.id"))
    tenant_id          = Column(String, nullable=False)
    client_id          = Column(String, nullable=False, unique=True)
    client_secret      = Column(String, nullable=False)
    credential_status  = Column(String, default="Active")
    last_token_refresh = Column(DateTime)
    created_at         = Column(DateTime)
    updated_at         = Column(DateTime)


class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"

    id          = Column(Integer, primary_key=True)
    account_id  = Column(Integer, ForeignKey("accounts.id"))
    credentials = Column(JSONB)   # encrypted blob — decrypt via EncryptionManager
    is_active   = Column(Boolean, default=True)
    last_synced = Column(DateTime)
    created_at  = Column(DateTime)
    updated_at  = Column(DateTime)


class AccountSmtpCredential(Base):
    __tablename__ = "account_smtp_credentials"

    id                 = Column(Integer, primary_key=True)
    account_id         = Column(Integer, ForeignKey("accounts.id"), unique=True, nullable=False)
    smtp_email         = Column(String, nullable=False)
    is_active          = Column(Boolean, default=True)
    created_at         = Column(DateTime)
    updated_at         = Column(DateTime)
    azure_tenant_id    = Column(String, nullable=False)
    azure_client_id    = Column(String, nullable=False)
    azure_client_secret = Column(String, nullable=False)
