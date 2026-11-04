"""Vercel entry point for the existing FastAPI application."""

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend" / "dist"
if FRONTEND_DIR.is_dir() and hasattr(app, "frontend"):
    app.frontend("/", directory=str(FRONTEND_DIR), fallback="index.html")
