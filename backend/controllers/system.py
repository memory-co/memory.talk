from fastapi import APIRouter

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health", summary="健康检查")
def health():
    return {"ok": True}
