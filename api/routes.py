"""The machine surface: `/api/v1`. Routes are added in stage 1b (enacted view,
stat pages, labels, status) and stage 2 (the compiled view)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from params import public_cache

api = APIRouter(prefix="/api/v1", tags=["api"], dependencies=[Depends(public_cache)])
