from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.workbench import router as workbench_router
from app.api.v1.files import router as files_router
from app.api.v1.models import router as models_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.documents import router as documents_router
from app.api.v1.runs import router as runs_router
from app.api.v1.ocr import router as ocr_router
from app.api.v1.pdf import router as pdf_router
from app.api.v1.sandbox import router as sandbox_router
from app.api.v1.security import router as security_router
from app.api.v1.system import router as system_router
from app.api.v1.settings import router as settings_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(workbench_router)
api_router.include_router(files_router)
api_router.include_router(models_router)
api_router.include_router(knowledge_router)
api_router.include_router(documents_router)
api_router.include_router(runs_router)
api_router.include_router(ocr_router)
api_router.include_router(pdf_router)
api_router.include_router(sandbox_router)
api_router.include_router(security_router)
api_router.include_router(system_router)
api_router.include_router(settings_router)
