"""小程序 API 路由聚合"""

from fastapi import APIRouter

from app.routers.mp import auth, user, analysis, reports, chat, membership, notifications, stocks, favorites, news, risk_messages, push

router = APIRouter(prefix="/api/mp", tags=["miniprogram"])

router.include_router(auth.router)
router.include_router(user.router)
router.include_router(membership.router)
router.include_router(notifications.router)
router.include_router(push.router)
router.include_router(risk_messages.router)
router.include_router(analysis.router)
router.include_router(reports.router)
router.include_router(chat.router)
router.include_router(stocks.router)
router.include_router(favorites.router)
router.include_router(news.router)
