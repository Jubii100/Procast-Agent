"""Authentication middleware for JWT integration."""

from dataclasses import dataclass
from typing import Optional

import structlog
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import settings
import jwt
from jwt import InvalidTokenError

logger = structlog.get_logger(__name__)

# Security scheme for OpenAPI docs
security_scheme = HTTPBearer(auto_error=False)


@dataclass
class UserContext:
    """User context extracted from authentication."""
    
    user_id: str
    email: Optional[str] = None
    roles: list[str] = None
    scopes: list[str] = None
    
    def __post_init__(self):
        if self.roles is None:
            self.roles = []
        if self.scopes is None:
            self.scopes = ["budget:read", "budget:analyze"]
    
    def has_scope(self, scope: str) -> bool:
        """Check if user has a specific scope."""
        return scope in self.scopes
    
    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware.
    
    Validates JWT tokens from Authorization header.
    """
    
    # Paths that don't require authentication
    PUBLIC_PATHS = {"/health", "/api/v1/health", "/docs", "/openapi.json", "/redoc"}
    
    async def dispatch(self, request: Request, call_next):
        """Process the request through authentication."""
        # Skip auth for public paths
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)
        
        # Get user context
        user_context = await self._get_user_context(request)
        
        if user_context is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing or invalid authorization token"},
            )
        
        # Attach user context to request state
        request.state.user = user_context
        
        return await call_next(request)
    
    async def _get_user_context(self, request: Request) -> Optional[UserContext]:
        """
        Extract user context from request.
        
        Extracts and validates JWT token from Authorization header.
        """
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        return await self._validate_jwt(token)
    
    async def _validate_jwt(self, token: str) -> Optional[UserContext]:
        """
        Validate JWT token and extract user context.
        
        Expected JWT claims:
        - sub: User ID
        - email: User email
        - roles: User roles
        - scope: Granted scopes
        """
        if not settings.jwt_secret_key:
            logger.error("JWT secret key not configured")
            return None

        try:
            decode_kwargs = {
                "key": settings.jwt_secret_key,
                "algorithms": [settings.jwt_algorithm],
                "options": {"require": ["sub"]},
            }
            if settings.jwt_audience:
                decode_kwargs["audience"] = settings.jwt_audience
            if settings.jwt_issuer:
                decode_kwargs["issuer"] = settings.jwt_issuer

            payload = jwt.decode(token, **decode_kwargs)
            scopes = payload.get("scope", "")
            if isinstance(scopes, str):
                scopes_list = scopes.split()
            else:
                scopes_list = list(scopes or [])

            roles = payload.get("roles", [])
            if not isinstance(roles, list):
                roles = [roles]

            return UserContext(
                user_id=payload["sub"],
                email=payload.get("email"),
                roles=roles,
                scopes=scopes_list,
            )
        except InvalidTokenError as e:
            logger.warning("Invalid JWT token", error=str(e))
            return None


async def get_current_user(request: Request) -> UserContext:
    """
    Dependency to get current user context.
    
    Uses request state if available (from middleware),
    otherwise falls back to headers or mock user.
    """
    # Try to get from request state (set by middleware)
    if hasattr(request.state, "user"):
        return request.state.user
    
    # No user context -> unauthorized
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authorization token",
    )


def require_scope(scope: str):
    """
    Dependency factory to require a specific scope.
    
    Usage:
        @router.get("/admin", dependencies=[Depends(require_scope("admin:read"))])
    """
    async def check_scope(user: UserContext = get_current_user) -> UserContext:
        if not user.has_scope(scope):
            raise HTTPException(
                status_code=403,
                detail=f"Missing required scope: {scope}",
            )
        return user
    
    return check_scope
