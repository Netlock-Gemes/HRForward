from fastapi import Request
from fastapi.responses import RedirectResponse

from .config import Config


def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated") is True


def require_auth(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(
            "/login",
            status_code=303,
        )

    return None


def authenticate(
    request: Request,
    username: str,
    password: str,
    config: Config,
) -> bool:
    if (
        username == config.admin_username
        and password == config.admin_password
    ):
        request.session["authenticated"] = True
        return True

    return False


def logout(request: Request) -> None:
    request.session.clear()