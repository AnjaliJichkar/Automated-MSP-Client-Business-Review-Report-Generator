"""
Entry Point for Local Development
Runs the FastAPI application using uvicorn server
"""
if __name__ == "__main__":
    import uvicorn
    from app.main import app

    # Run the FastAPI app locally
    # - host: localhost only (change to 0.0.0.0 for external access)
    # - port: 8080 (default port for this application)
    # - reload: Auto-reload on code changes (development only)
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="info", reload=True)
