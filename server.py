from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import auth
import files
import live
import web

APP_ORIGINS = ["http://localhost", "https://localhost", "capacitor://localhost"]


def create_app(latest, library, lifespan=None, web_dir=None, access_token=None):
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(auth.TokenAuthMiddleware, token=access_token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=APP_ORIGINS,
        allow_methods=["GET"],
        allow_headers=["Authorization"],
    )

    app.include_router(live.create_router(latest))
    app.include_router(files.create_router(library))

    if web_dir is not None:
        web.mount_web(app, web_dir)

    return app
