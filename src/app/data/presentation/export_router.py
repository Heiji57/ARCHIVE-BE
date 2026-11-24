"""내보내기 API(12 §2)."""

from datetime import UTC, datetime

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.data.application.ports import ExportStorage
from app.data.application.use_cases.exports import GetExportUseCase, RequestExportUseCase
from app.data.domain.exceptions.exceptions import ExportNotFoundException
from app.data.domain.models.export import EXPORT_URL_TTL, ExportJob
from app.data.presentation.requests.requests import RequestExportRequest
from app.data.presentation.responses.responses import ExportCreatedResponse, ExportResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import (
    create_export_download_token,
    decode_export_download_token,
    get_current_user,
)
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/exports", tags=["data"], route_class=DishkaRoute)


def _enqueue_build(export_id: str) -> None:
    from app.worker.tasks.exports import build_export_task

    build_export_task.apply_async(args=[export_id], queue="default")


def _view(job: ExportJob) -> ExportResponse:
    url = None
    if job.status == "ready" and job.file_key:
        token = create_export_download_token(job.id, EXPORT_URL_TTL)
        url = f"/api/v1/exports/{job.id}/download?token={token}"
    return ExportResponse(
        id=job.id,
        status=job.status,
        scopes=list(job.scopes),
        format=job.format,
        created_at=job.created_at,
        download_url=url,
        expires_at=job.expires_at,
    )


@router.post(
    "", status_code=status.HTTP_202_ACCEPTED, response_model=ApiResponse[ExportCreatedResponse]
)
async def request_export(
    body: RequestExportRequest,
    background_tasks: BackgroundTasks,
    use_case: FromDishka[RequestExportUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[ExportCreatedResponse]:
    """사용자당 동시에 하나, 최근 24시간 3번. 완료되면 알림(category: system)."""
    job = await use_case.execute(current_user.id, body.scopes, body.format)
    # BackgroundTasks 는 이 스택에서 요청 커밋보다 먼저 돌 수 있다 — 워커가 행이 안 보이면
    # 잠시 뒤 다시 시도한다(worker/tasks/exports.py).
    background_tasks.add_task(_enqueue_build, job.id)
    return ApiResponse.ok(ExportCreatedResponse(id=job.id))


@router.get("/{export_id}", response_model=ApiResponse[ExportResponse])
async def get_export(
    export_id: str,
    use_case: FromDishka[GetExportUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[ExportResponse]:
    return ApiResponse.ok(_view(await use_case.execute(current_user.id, export_id)))


@router.get(
    "/{export_id}/download",
    response_class=Response,
    responses={
        200: {"description": "zip (로컬 저장)", "content": {"application/zip": {}}},
        307: {"description": "객체 저장소의 서명 URL(5분)로 이동 — `Location`"},
    },
)
async def download_export(
    export_id: str,
    use_case: FromDishka[GetExportUseCase],
    storage: FromDishka[ExportStorage],
    token: str = Query(...),
) -> Response:
    """서명 URL(24시간) — 로그인 헤더 없이 브라우저가 바로 받는다.

    객체 저장소면 5분짜리 저장소 서명 URL 로 307, 로컬이면 파일을 직접 보낸다.
    """
    if decode_export_download_token(token) != export_id:
        raise ExportNotFoundException()
    download = await use_case.execute_by_id(export_id, datetime.now(UTC))
    job = download.job
    filename = f"archive-export-{download.created_on.isoformat()}.zip"
    found = await storage.locate(job.file_key, filename) if job.file_key else None
    if found is None:
        raise ExportNotFoundException()
    if found.url is not None:
        return RedirectResponse(found.url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    assert found.path is not None
    return FileResponse(found.path, media_type="application/zip", filename=filename)
