from fastapi import (
    APIRouter,
    Form,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)

from .auth import authenticate, logout, require_auth
from .config import Config
from .database import Database


def create_router(
    config: Config,
    database: Database,
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/login",
        response_class=HTMLResponse,
    )
    async def login_page(
        request: Request,
    ):
        if request.session.get("authenticated"):
            return RedirectResponse(
                "/",
                status_code=303,
            )

        return request.app.state.templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": None},
        )

    @router.post("/login")
    async def login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ):
        if authenticate(
            request,
            username,
            password,
            config,
        ):
            return RedirectResponse(
                "/",
                status_code=303,
            )

        return request.app.state.templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Invalid username or password"
            },
            status_code=401,
        )

    @router.get(
        "/",
        response_class=HTMLResponse,
    )
    async def dashboard(
        request: Request,
    ):
        redirect = require_auth(request)

        if redirect:
            return redirect

        routes = await database.get_routes()

        return request.app.state.templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"routes": routes},
        )

    @router.post("/routes")
    async def create_route(
        request: Request,
        name: str = Form(...),
        sources: str = Form(...),
        destinations: str = Form(...),
        delay_seconds: int = Form(0),
    ):
        redirect = require_auth(request)

        if redirect:
            return redirect

        source_list = _parse_chat_ids(sources)
        destination_list = _parse_chat_ids(destinations)

        # Prevent invalid negative delays.
        delay_seconds = max(0, delay_seconds)

        if not source_list or not destination_list:
            return RedirectResponse(
                "/",
                status_code=303,
            )

        await database.create_route(
            name=name.strip(),
            sources=source_list,
            destinations=destination_list,
            delay_seconds=delay_seconds,
        )

        return RedirectResponse(
            "/",
            status_code=303,
        )

    @router.post(
        "/routes/{route_id}/update"
    )
    async def update_route(
        request: Request,
        route_id: str,
        name: str = Form(...),
        sources: str = Form(...),
        destinations: str = Form(...),
        delay_seconds: int = Form(0),
    ):
        redirect = require_auth(request)

        if redirect:
            return redirect

        source_list = _parse_chat_ids(sources)
        destination_list = _parse_chat_ids(destinations)

        # Prevent invalid negative delays.
        delay_seconds = max(0, delay_seconds)

        if not source_list or not destination_list:
            return RedirectResponse(
                "/",
                status_code=303,
            )

        routes = await database.get_routes()

        route = next(
            (
                route
                for route in routes
                if route["_id"] == route_id
            ),
            None,
        )

        if route:
            await database.update_route(
                route_id=route_id,
                name=name.strip(),
                sources=source_list,
                destinations=destination_list,
                delay_seconds=delay_seconds,
                enabled=route["enabled"],
            )

        return RedirectResponse(
            "/",
            status_code=303,
        )

    @router.post(
        "/routes/{route_id}/delete"
    )
    async def delete_route(
        request: Request,
        route_id: str,
    ):
        redirect = require_auth(request)

        if redirect:
            return redirect

        await database.delete_route(route_id)

        return RedirectResponse(
            "/",
            status_code=303,
        )

    @router.post(
        "/routes/{route_id}/toggle"
    )
    async def toggle_route(
        request: Request,
        route_id: str,
    ):
        redirect = require_auth(request)

        if redirect:
            return redirect

        routes = await database.get_routes()

        route = next(
            (
                route
                for route in routes
                if route["_id"] == route_id
            ),
            None,
        )

        if route:
            await database.update_route(
                route_id=route_id,
                name=route["name"],
                sources=route["sources"],
                destinations=route["destinations"],
                delay_seconds=route.get(
                    "delay_seconds",
                    0,
                ),
                enabled=not route["enabled"],
            )

        return RedirectResponse(
            "/",
            status_code=303,
        )

    @router.get("/logout")
    async def logout_route(
        request: Request,
    ):
        logout(request)

        return RedirectResponse(
            "/login",
            status_code=303,
        )

    return router


def _parse_chat_ids(
    value: str,
):
    result = []

    for item in value.split(","):
        item = item.strip()

        if not item:
            continue

        if item.lstrip("-").isdigit():
            result.append(int(item))
        else:
            result.append(item)

    return result