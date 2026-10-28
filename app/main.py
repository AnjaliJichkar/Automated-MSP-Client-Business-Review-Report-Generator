
from dotenv import load_dotenv
load_dotenv()
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
import secrets
import os

# Configure logging
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
    force=True,   # override any handlers uvicorn already attached to root logger
)
logger = logging.getLogger(__name__)

# --- Documentation Authentication Setup ---
security = HTTPBasic()
DOCS_USERNAME = os.getenv("DOCS_USERNAME", "admin")
DOCS_PASSWORD = os.getenv("DOCS_PASSWORD", "changeme")

def verify_docs_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Verify documentation access credentials using Basic HTTP Authentication.
    Uses secrets.compare_digest to prevent timing attacks.
    """
    correct_username = secrets.compare_digest(credentials.username, DOCS_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, DOCS_PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials for documentation access",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

# --- FastAPI Application Setup ---
app = FastAPI(
    title="FastAPI Microsoft Graph Client",
    version="2.0.0",
    description="A flexible FastAPI service to query various Microsoft Graph API v1.0 and beta endpoints.",
    docs_url=None,  # Disable default docs - we'll add protected version below
    redoc_url=None  # Disable default redoc - we'll add protected version below
)

# CORS — origins controlled via ALLOWED_ORIGINS env var
# Dev/Local: ALLOWED_ORIGINS=*
# Stage/Prod: ALLOWED_ORIGINS=https://your-frontend.com,https://www.your-frontend.com
import os as _os
_cors_env = _os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = ["*"] if _cors_env.strip() == "*" else [o.strip() for o in _cors_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Protected Documentation Endpoints ---
@app.get("/docs", include_in_schema=False)
async def get_documentation(authenticated: bool = Depends(verify_docs_credentials)):
    """
    Protected Swagger UI documentation.
    Requires username and password authentication.
    """
    return get_swagger_ui_html(openapi_url="/openapi.json", title="API Documentation")

@app.get("/redoc", include_in_schema=False)
async def get_redoc(authenticated: bool = Depends(verify_docs_credentials)):
    """
    Protected ReDoc documentation.
    Requires username and password authentication.
    """
    return get_redoc_html(openapi_url="/openapi.json", title="API Documentation - ReDoc")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Custom validation error handler for better user experience"""
    error_details = []
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error["loc"])
        error_details.append({
            "field": field_path,
            "message": error["msg"],
            "invalid_value": error.get("input", "N/A")
        })

    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation failed",
            "status_code": 422,
            "details": error_details,
            "message": "Please check the provided data and try again"
        }
    )


# Import routers from routes folder
from app.routes.health_check import router as health_check_router
from app.routes.security.issues import router as security_router
from app.routes.security.mfa import router as mfa_router
from app.routes.admin.licenses import router as license_router
from app.routes.clients.users import router as user_router
from app.routes.security.secure_score import router as secure_router
from app.routes.compliance.status import router as all_router
from app.routes.compliance.status_post import router as post_router
from app.routes.admin.clients import router as client_router
from app.routes.security.reports import router as report_router
from app.routes.security.cache_test import router as cache_test_router
from app.routes.clients.charts import router as integration_platform_router
from app.routes.reports.send_poc_email import router as send_poc_email_router
from app.routes.reports.download_pdf import router as download_router
from app.routes.reports.llm_report import router as llm_report_router



# Include all routers with /api prefix
app.include_router(health_check_router, prefix="/api", tags=["health check"])
app.include_router(mfa_router, prefix="/api", tags=["mfa"])
app.include_router(secure_router, prefix="/api", tags=["microsoft secure"])
app.include_router(security_router, prefix="/api", tags=["security"])
app.include_router(all_router, prefix="/api", tags=[ "compliance status get endpoints"])
app.include_router(post_router, prefix="/api", tags=["complaince status post endpoints"])
app.include_router(license_router, prefix="/api", tags=["licenses overview"])
app.include_router(user_router, prefix="/api", tags=["users dashboard"])
app.include_router(client_router, prefix="/api",tags=["client page"])
app.include_router(report_router, prefix="/api", tags=["security reports"])
app.include_router(cache_test_router, prefix="/api", tags=["cache testing"])
app.include_router(integration_platform_router, prefix="/api", tags=["integration platforms"])
app.include_router(send_poc_email_router, prefix="/api", tags=["POC email reports"])
app.include_router(download_router, prefix="/api", tags=["PDF Download"])
app.include_router(llm_report_router, prefix="/api", tags=["LLM Reports"])

# Configure static file serving for PDF reports
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")





