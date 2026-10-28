# app/models/reports.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database.engine import Base


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    id                = Column(Integer, primary_key=True)
    organization_id   = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    report_month      = Column(String, nullable=False)
    report_year       = Column(Integer, nullable=False)
    organization_data = Column(JSONB)
    file_path         = Column(String)
    file_url          = Column(String)
    pdf_generated_at  = Column(DateTime)
    status            = Column(String, default="Active")
    generated_at      = Column(DateTime)
    created_at        = Column(DateTime)
    updated_at        = Column(DateTime)
    llm_data          = Column(JSONB)
    report_type       = Column(String)


