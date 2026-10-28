# app/models/organizations.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from app.core.database.engine import Base


class Organization(Base):
    __tablename__ = "organizations"

    id                = Column(Integer, primary_key=True)
    account_id        = Column(Integer, ForeignKey("accounts.id"))
    organization_name = Column(String, nullable=False)
    domain            = Column(String)
    industry          = Column(String)
    organization_size = Column(String)
    status            = Column(String, default="Active")
    created_at        = Column(DateTime)
    updated_at        = Column(DateTime)


class OrganizationPoc(Base):
    __tablename__ = "organization_pocs"

    id              = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    poc_name        = Column(String, nullable=False)
    poc_email       = Column(String, nullable=False, unique=True)
    poc_role        = Column(String)
    created_at      = Column(DateTime)
    updated_at      = Column(DateTime)
    is_active       = Column(Boolean, nullable=False, default=True)


class OrganizationIntegration(Base):
    __tablename__ = "organization_integrations"

    id                       = Column(Integer, primary_key=True)
    organization_id          = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    integration_id           = Column(Integer, ForeignKey("integrations.id"), nullable=False)
    platform_organization_id = Column(String, nullable=False)
    is_active                = Column(Boolean, default=True)
    last_synced              = Column(DateTime)
    created_at               = Column(DateTime)
    updated_at               = Column(DateTime)


class OrganizationMapping(Base):
    """Legacy mapping table linking NinjaOne/Autotask/ConnectSecure org IDs."""
    __tablename__ = "organization_mapping"

    id                      = Column(Integer, primary_key=True)
    ninjaone_org_id         = Column(String)
    organization_name       = Column(String)
    autotask_company_id     = Column(String)
    connectsecure_company_id = Column(String)
    last_synced             = Column(DateTime)
