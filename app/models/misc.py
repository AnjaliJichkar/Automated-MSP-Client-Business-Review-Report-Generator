# app/models/misc.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database.engine import Base


class LicenseSkuMapping(Base):
    __tablename__ = "license_sku_mappings"

    id                   = Column(Integer, primary_key=True)
    service_plan_name    = Column(String, nullable=False, unique=True)
    product_display_name = Column(String, nullable=False)
    created_at           = Column(DateTime)
    updated_at           = Column(DateTime)


class ApiCallLog(Base):
    __tablename__ = "api_call_logs"

    id               = Column(Integer, primary_key=True)
    account_id       = Column(Integer, ForeignKey("accounts.id"))
    organization_id  = Column(Integer, ForeignKey("organizations.id"))
    integration_name = Column(String)
    endpoint         = Column(String, nullable=False)
    method           = Column(String, nullable=False)
    status_code      = Column(Integer)
    response_time_ms = Column(Integer)
    error_message    = Column(Text)
    called_at        = Column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id              = Column(Integer, primary_key=True)
    account_id      = Column(Integer, ForeignKey("accounts.id"))
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    platform_user_id = Column(Integer, ForeignKey("platform_users.id"))
    action          = Column(String, nullable=False)
    entity_type     = Column(String)
    entity_id       = Column(String)
    details         = Column(JSONB)
    ip_address      = Column(String)
    created_at      = Column(DateTime)
