from fastapi import FastAPI

import files
import live
import web


def create_app(latest, library, lifespan=None, web_dir=None):
    app = FastAPI(lifespan=lifespan)

    app.include_router(live.create_router(latest))
    app.include_router(files.create_router(library))

    if web_dir is not None:
        web.mount_web(app, web_dir)

    return app
