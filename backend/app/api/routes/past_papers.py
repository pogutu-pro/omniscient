from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_past_paper_repo, get_settings_dep
from app.core.config import Settings
from app.repositories.past_paper_repository import PastPaperRepository
from app.schemas.past_paper import PastPaperOut, PastPaperSearchParams
from app.services.storage.factory import get_storage_backend

router = APIRouter(prefix="/api/past-papers", tags=["past_papers"])


@router.get("", response_model=list[PastPaperOut])
async def search_past_papers(
    query: str | None = Query(default=None),
    course_code: str | None = Query(default=None),
    programme_code: str | None = Query(default=None),
    academic_year: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    repo: PastPaperRepository = Depends(get_past_paper_repo),
) -> list[PastPaperOut]:
    params = PastPaperSearchParams(
        query=query, course_code=course_code, programme_code=programme_code, academic_year=academic_year, limit=limit
    )
    return await repo.search(params)


@router.get("/{paper_id}", response_model=PastPaperOut)
async def get_past_paper(paper_id: str, repo: PastPaperRepository = Depends(get_past_paper_repo)) -> PastPaperOut:
    paper = await repo.get_by_id(paper_id)
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Past paper not found")
    return paper


@router.get("/{paper_id}/download")
async def download_past_paper(
    paper_id: str,
    repo: PastPaperRepository = Depends(get_past_paper_repo),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    paper = await repo.get_by_id(paper_id)
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Past paper not found")
    storage = get_storage_backend(settings)
    try:
        content = await storage.read(paper.file_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not available") from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{paper.file_name}"'},
    )
