"""v1 路由聚合：六域（WS 单独挂根路径，前缀含 /api/v1，见契约 §4）。"""

from fastapi import APIRouter

from app.api.v1 import alert, control, hardware, metrics, monitor, report, storage, system

api_router = APIRouter()
api_router.include_router(monitor.router)
api_router.include_router(storage.router)
api_router.include_router(system.router)
api_router.include_router(control.router)
api_router.include_router(alert.router)
api_router.include_router(report.router)
api_router.include_router(hardware.router)
api_router.include_router(metrics.router)
