"""FastAPI application for memory-talk server."""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from memory_talk.api import router, set_source_manager
from memory_talk.web.app import SourceManager


def _init_default_subjects():
    """Initialize default subjects if they don't exist."""
    from memory_talk.models import Subject
    from memory_talk.storage import Storage

    storage = Storage()

    default_subjects = [
        Subject(
            id="human-default",
            name="Human User",
            match="role == 'user'",
            priority=10,
            metadata={"description": "Default human user"},
        ),
        Subject(
            id="ai-assistant",
            name="AI Assistant",
            match="role == 'assistant'",
            priority=10,
            metadata={"description": "Default AI assistant"},
        ),
    ]

    for subject in default_subjects:
        existing = storage.get_subject(subject.id)
        if existing is None:
            storage.create_subject(subject)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="memory-talk",
        description="Local server for storing conversation data from various chat platforms",
        version="0.1.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize source manager
    source_manager = SourceManager()
    set_source_manager(source_manager)

    # Include API routes
    app.include_router(router)

    # Initialize default subjects
    _init_default_subjects()

    # Setup templates
    templates = Jinja2Templates(directory=Path(__file__).parent / "web" / "templates")

    @app.get("/")
    async def root():
        """Render the main dashboard."""
        from fastapi.requests import Request
        return templates.TemplateResponse("dashboard.html", {"request": {}})

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok"}

    return app


app = create_app()


def run_server(host: str = "localhost", port: int = 7788, reload: bool = False):
    """Run the server.

    Args:
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload
    """
    import uvicorn
    uvicorn.run(
        "memory_talk.server:app",
        host=host,
        port=port,
        reload=reload,
    )
