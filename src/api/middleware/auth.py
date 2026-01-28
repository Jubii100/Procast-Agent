"""Authentication middleware for JWT integration (pre-JWT mock implementation)."""

from dataclasses import dataclass
from typing import Optional

import structlog
from fastapi import Header, HTTPException, Request
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import settings

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
    
    Currently implements mock authentication using X-User-ID header.
    Will be updated to validate JWT tokens when .NET backend integration is ready.
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
            # For now, create a mock user for testing
            # In production, this would raise 401
            user_context = UserContext(
                user_id=settings.mock_user_id,
                email=settings.mock_user_email,
            )
            logger.debug("Using mock user context", user_id=user_context.user_id)
        
        # Attach user context to request state
        request.state.user = user_context
        
        return await call_next(request)
    
    async def _get_user_context(self, request: Request) -> Optional[UserContext]:
        """
        Extract user context from request.
        
        Currently checks for X-User-ID header (mock auth).
        Will be updated for JWT validation.
        """
        # Check for mock auth header
        user_id = request.headers.get("X-User-ID")
        if user_id:
            email = request.headers.get("X-User-Email")
            return UserContext(user_id=user_id, email=email)
        
        # TODO: Implement JWT validation
        # auth_header = request.headers.get("Authorization")
        # if auth_header and auth_header.startswith("Bearer "):
        #     token = auth_header[7:]
        #     return await self._validate_jwt(token)
        
        return None
    
    async def _validate_jwt(self, token: str) -> Optional[UserContext]:
        """
        Validate JWT token and extract user context.
        
        TODO: Implement when .NET backend provides JWT specs.
        
        Expected JWT claims:
        - sub: User ID
        - email: User email
        - roles: User roles
        - scope: Granted scopes
        """
        # Placeholder for JWT validation
        # import jwt
        # try:
        #     payload = jwt.decode(
        #         token,
        #         settings.jwt_secret_key,
        #         algorithms=[settings.jwt_algorithm],
        #         audience=settings.jwt_audience,
        #         issuer=settings.jwt_issuer,
        #     )
        #     return UserContext(
        #         user_id=payload["sub"],
        #         email=payload.get("email"),
        #         roles=payload.get("roles", []),
        #         scopes=payload.get("scope", "").split(),
        #     )
        # except jwt.InvalidTokenError as e:
        #     logger.warning("Invalid JWT token", error=str(e))
        #     return None
        pass


async def get_current_user(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> UserContext:
    """
    Dependency to get current user context.
    
    Uses request state if available (from middleware),
    otherwise falls back to headers or mock user.
    """
    # Try to get from request state (set by middleware)
    if hasattr(request.state, "user"):
        return request.state.user
    
    # Fall back to headers
    if x_user_id:
        return UserContext(user_id=x_user_id, email=x_user_email)
    
    # Use mock user for local development
    return UserContext(
        user_id=settings.mock_user_id,
        email=settings.mock_user_email,
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
