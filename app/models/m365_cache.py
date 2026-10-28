# app/models/m365_cache.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from app.core.database.engine import Base


class M365User(Base):
    __tablename__ = "m365_users"

    id                  = Column(Integer, primary_key=True)
    organization_id     = Column(Integer, ForeignKey("organizations.id"))
    user_id             = Column(String, nullable=False, unique=True)
    display_name        = Column(String)
    email               = Column(String)
    department          = Column(String)
    role                = Column(String)
    status              = Column(String)
    mfa_enabled         = Column(Boolean, default=False)
    user_principal_name = Column(String)
    last_synced         = Column(DateTime)
    user_type           = Column(String, default="Member")


class M365UserDetail(Base):
    __tablename__ = "m365_user_details"

    id                                  = Column(Integer, primary_key=True)
    user_id                             = Column(String, ForeignKey("m365_users.user_id"))
    licenses                            = Column(ARRAY(String))
    mailbox_size_mb                     = Column(Integer)
    mailbox_quota_mb                    = Column(Integer)
    mailbox_usage_percentage            = Column(Numeric)
    mailbox_items_count                 = Column(Integer)
    mailbox_archived_items_count        = Column(Integer)
    onedrive_size_mb                    = Column(Integer)
    onedrive_quota_mb                   = Column(Integer)
    onedrive_usage_percentage           = Column(Numeric)
    onedrive_files_count                = Column(Integer)
    teams_calls_minutes_last_30_days    = Column(Integer, default=0)
    teams_meetings_count_last_30_days   = Column(Integer, default=0)
    teams_messages_count_last_30_days   = Column(Integer, default=0)
    email_sent_count_last_30_days       = Column(Integer, default=0)
    documents_edited_last_30_days       = Column(Integer, default=0)
    risk_level                          = Column(String)
    sign_in_attempts_last_30_days       = Column(Integer)
    blocked_sign_in_attempts            = Column(Integer)
    authentication_methods              = Column(ARRAY(String))
    last_password_change                = Column(DateTime)
    last_sign_in                        = Column(DateTime)
    groups                              = Column(ARRAY(String))
    last_updated                        = Column(DateTime)


class M365UserDevice(Base):
    __tablename__ = "m365_user_devices"

    id          = Column(Integer, primary_key=True)
    device_id   = Column(String, nullable=False)
    device_name = Column(String)
    device_type = Column(String)
    last_synced = Column(DateTime)
    user_id     = Column(String, ForeignKey("m365_users.user_id"))


class M365ComplianceSnapshot(Base):
    __tablename__ = "m365_compliance_snapshots"

    id              = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    status          = Column(String)
    score_percentage = Column(Integer)
    total_policies  = Column(Integer)
    policies_data   = Column(JSONB)
    checked_at      = Column(DateTime)
    breakdown       = Column(JSONB)
    title           = Column(String, default="Microsoft 365 Compliance Status")


class M365MfaSnapshot(Base):
    __tablename__ = "m365_mfa_snapshots"

    id                 = Column(Integer, primary_key=True)
    organization_id    = Column(Integer, ForeignKey("organizations.id"))
    percentage         = Column(Numeric)
    status             = Column(String)
    total_users        = Column(Integer)
    mfa_enabled        = Column(Integer)
    mfa_disabled       = Column(Integer)
    mfa_registered     = Column(Integer)
    conditional_access = Column(Integer, default=0)
    security_defaults  = Column(Integer, default=0)
    per_user_mfa       = Column(Integer, default=0)
    recommendation     = Column(Text)
    description        = Column(Text)
    measurement_date   = Column(DateTime)


class M365LicenseSnapshot(Base):
    __tablename__ = "m365_license_snapshots"

    id              = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    total_users     = Column(Integer)
    others_count    = Column(Integer, default=0)
    standard_count  = Column(Integer, default=0)
    premium_count   = Column(Integer, default=0)
    basic_count     = Column(Integer, default=0)
    license_details = Column(JSONB)
    snapshot_date   = Column(DateTime)


class M365SecureScoreHistory(Base):
    __tablename__ = "m365_secure_score_history"

    id                      = Column(Integer, primary_key=True)
    organization_id         = Column(Integer, ForeignKey("organizations.id"))
    current_score           = Column(Numeric)
    max_score               = Column(Numeric)
    percentage              = Column(Numeric)
    active_user_count       = Column(Integer)
    licensed_user_count     = Column(Integer)
    top_improvement_actions = Column(JSONB)
    all_improvement_actions = Column(JSONB)
    completed_actions       = Column(JSONB)
    created_at              = Column(DateTime)
    score_data              = Column(JSONB)


class M365RiskySignin(Base):
    __tablename__ = "m365_risky_signins"

    id                                   = Column(Integer, primary_key=True)
    organization_id                      = Column(Integer, ForeignKey("organizations.id"))
    event_id                             = Column(String, nullable=False, unique=True)
    user_display_name                    = Column(String)
    user_id                              = Column(String)
    user_principal_name                  = Column(String)
    ip_address                           = Column(String)
    client_app_used                      = Column(String)
    correlation_id                       = Column(String)
    conditional_access_status            = Column(String)
    applied_conditional_access_policies  = Column(JSONB)
    is_interactive                       = Column(Boolean)
    device_detail                        = Column(JSONB)
    location                             = Column(JSONB)
    risk_detail                          = Column(String)
    risk_level_aggregated                = Column(String)
    risk_level_during_signin             = Column(String)
    risk_state                           = Column(String)
    risk_event_types                     = Column(ARRAY(String))
    risk_event_types_v2                  = Column(ARRAY(String))
    resource_display_name                = Column(String)
    resource_id                          = Column(String)
    status                               = Column(JSONB)
    app_display_name                     = Column(String)
    app_id                               = Column(String)
    created_date_time                    = Column(DateTime)
    last_synced                          = Column(DateTime)


class M365RiskyUser(Base):
    __tablename__ = "m365_risky_users"

    id                  = Column(Integer, primary_key=True)
    organization_id     = Column(Integer, ForeignKey("organizations.id"))
    user_id             = Column(String, nullable=False)
    user_principal_name = Column(String)
    display_name        = Column(String)
    risk_level          = Column(String)
    risk_state          = Column(String)
    risk_detail         = Column(String)
    risk_last_updated   = Column(DateTime)
    is_deleted          = Column(Boolean, default=False)
    is_processing       = Column(Boolean, default=False)
    detected_at         = Column(DateTime)
    resolved_at         = Column(DateTime)
    remediation_action  = Column(String)


class M365SecurityAlert(Base):
    __tablename__ = "m365_security_alerts"

    id              = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    alert_id        = Column(String, nullable=False, unique=True)
    alert_type      = Column(String)
    title           = Column(String)
    description     = Column(Text)
    severity        = Column(String)
    status          = Column(String)
    category        = Column(String)
    created_at      = Column(DateTime)
    last_updated    = Column(DateTime)
    service_source  = Column(String)
    affected_user   = Column(String)
    ip_address      = Column(String)
    location        = Column(JSONB)
    raw_data        = Column(JSONB)
