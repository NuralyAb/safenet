"""Importing this package registers all source adapters."""
from app.workers.collectors import platforms  # noqa: F401  (triggers @register)
