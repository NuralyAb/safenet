from fastapi import APIRouter

from app.api.v1 import (
    accounts, analyze, auth, chat, graph, hunt, investigations, license, safenet, settings, triage,
    watchlist,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(investigations.router, prefix="/investigations", tags=["investigations"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(triage.router, prefix="/triage", tags=["triage"])
api_router.include_router(license.router, prefix="/license", tags=["license"])
api_router.include_router(analyze.router, prefix="/analyze", tags=["analyze"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(hunt.router, prefix="/hunt", tags=["hunt"])
api_router.include_router(safenet.router, prefix="/safenet", tags=["safenet"])
