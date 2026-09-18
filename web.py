from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
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
