"""Verify Supabase Auth access tokens at the API boundary."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from jwt import PyJWKClient


class AuthConfigurationError(RuntimeError):
    """Raised when the API has not been configured with an identity provider."""


class InvalidAccessToken(ValueError):
    """Raised when an access token is expired, malformed, or not from our issuer."""


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str | None = None


class SupabaseTokenVerifier:
    """Verify Supabase JWTs against the project's asymmetric public signing keys."""

    _ALLOWED_ALGORITHMS = {"ES256", "RS256", "EdDSA"}

    def __init__(self, project_url: str, audience: str = "authenticated") -> None:
        self.project_url = project_url.rstrip("/")
        self.issuer = f"{self.project_url}/auth/v1" if self.project_url else ""
        self.audience = audience
        jwks_url = f"{self.issuer}/.well-known/jwks.json" if self.issuer else ""
        self._jwks = PyJWKClient(jwks_url, cache_keys=True, timeout=5) if jwks_url else None

    def verify(self, token: str) -> AuthenticatedUser:
        if not self._jwks or not self.issuer:
            raise AuthConfigurationError("Supabase Auth is not configured.")

        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if algorithm not in self._ALLOWED_ALGORITHMS:
                raise InvalidAccessToken("Unsupported token signing algorithm.")

            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[algorithm],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "sub", "aud", "iss", "role"]},
            )
            if claims.get("role") != "authenticated":
                raise InvalidAccessToken("Token is not a user access token.")
            user_id = str(UUID(claims["sub"]))
            email = claims.get("email")
            return AuthenticatedUser(user_id=user_id, email=email if isinstance(email, str) else None)
        except InvalidAccessToken:
            raise
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise InvalidAccessToken("Invalid access token.") from exc
