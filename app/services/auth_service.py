import time
from datetime import timedelta
from typing import Literal, Optional

import jwt
from pydantic import BaseModel

from app.core.config import settings
from app.utils.timezone import now_tz

TokenType = Literal["access", "refresh"]


class TokenData(BaseModel):
    sub: str
    exp: int
    token_type: TokenType = "access"


class AuthService:
    @staticmethod
    def create_access_token(
        sub: str,
        expires_minutes: int | None = None,
        expires_delta: int | None = None,
        *,
        token_type: TokenType = "access",
    ) -> str:
        if expires_delta:
            expire = now_tz() + timedelta(seconds=expires_delta)
        elif token_type == "refresh":
            expire = now_tz() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        else:
            expire = now_tz() + timedelta(
                minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        payload = {"sub": sub, "exp": expire, "type": token_type}
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def create_refresh_token(sub: str) -> str:
        return AuthService.create_access_token(sub=sub, token_type="refresh")

    @staticmethod
    def verify_token(
        token: str,
        *,
        expected_type: Optional[TokenType] = "access",
    ) -> Optional[TokenData]:
        import logging

        logger = logging.getLogger(__name__)

        try:
            payload = jwt.decode(
                token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
            )
            sub = payload.get("sub")
            if not sub:
                return None

            # 兼容旧 token：无 type 时视为 access
            typ = payload.get("type") or "access"
            if expected_type and typ != expected_type:
                logger.warning("Token type mismatch: got=%s expected=%s", typ, expected_type)
                return None

            token_data = TokenData(
                sub=sub,
                exp=int(payload.get("exp", time.time())),
                token_type=typ,  # type: ignore[arg-type]
            )
            if token_data.exp < int(time.time()):
                return None
            return token_data
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token: %s", e)
            return None
        except Exception as e:
            logger.error("Token verify error: %s", e)
            return None
