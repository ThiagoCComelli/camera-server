from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

import auth

EXTERNAL_REDIRECT_URL = "https://google.com"


class SPAStaticFiles(StaticFiles):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not auth.is_local(
            (scope.get("client") or (None,))[0]
        ):
            response = RedirectResponse(EXTERNAL_REDIRECT_URL)
            return await response(scope, receive, send)
        return await super().__call__(scope, receive, send)

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if (
                exc.status_code != 404
                or path.startswith("api/")
                or "." in path.rsplit("/", 1)[-1]
            ):
                raise
            return await super().get_response("index.html", scope)


def mount_web(app: FastAPI, directory):
    app.mount("/", SPAStaticFiles(directory=directory, html=True), name="web")
