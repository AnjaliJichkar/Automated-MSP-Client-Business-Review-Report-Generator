# app/models/integrations.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database.engine import Base


class Integration(Base):
    __tablename__ = "integrations"

    id                       = Column(Integer, primary_key=True)
    integration_key          = Column(String, nullable=False, unique=True)
    integration_display_name = Column(String, nullable=False)
    description              = Column(Text)
    integration_fields       = Column(JSONB)
    is_active                = Column(Boolean, default=True)
    created_at               = Column(DateTime)
    updated_at               = Column(DateTime)
    json_object_name         = Column(Text, nullable=False)


class PlatformAvailableChart(Base):
    __tablename__ = "platform_available_charts"

    id                 = Column(Integer, primary_key=True)
    integration_id     = Column(Integer, ForeignKey("integrations.id"), nullable=False)
    chart_key          = Column(String, nullable=False)
    chart_display_name = Column(String, nullable=False)
    chart_description  = Column(Text)
    chart_type         = Column(String)
    json_path          = Column(String)
    created_at         = Column(DateTime)


class AccountSelectedChart(Base):
    __tablename__ = "account_selected_charts"

    id         = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    chart_id   = Column(Integer, ForeignKey("platform_available_charts.id"), nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    is_active  = Column(Boolean, nullable=False, default=True)
