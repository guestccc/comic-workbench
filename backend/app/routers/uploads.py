"""图片上传接口。"""

from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile

from ..schemas import UploadRead
from ..services.files import save_cover

router = APIRouter(prefix="/api/uploads", tags=["上传"])


@router.post("", response_model=UploadRead, status_code=201)
def upload_image(request: Request, file: UploadFile = File(...)) -> UploadRead:
    """上传封面图，返回服务端生成的文件名与可访问 URL。"""
    filename, url = save_cover(file, request.app.state.app_settings.upload_dir)
    return UploadRead(filename=filename, url=url)
