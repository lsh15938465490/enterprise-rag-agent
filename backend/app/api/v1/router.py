"""把所有 /api/v1 下的接口模块拼到一起。"""

from fastapi import APIRouter

from app.api.v1 import auth, chat, conversations, documents, health, knowledge_bases, tools, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(knowledge_bases.router)
api_router.include_router(documents.router)
api_router.include_router(conversations.router)
api_router.include_router(chat.router)
api_router.include_router(tools.router)
