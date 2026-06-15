from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from api.auth import router as auth_router
from api.contacts import router as contacts_router
from api.users import router as users_router
from conf.config import settings
from conf.limiter import limiter
from database.db import get_db

app = FastAPI(title="UMT pythonweb HW11")

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "Rate limit exceeded. Try again later."},
    )


app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(contacts_router, prefix="/api")


@app.get("/api/healthchecker")
def healthcheck(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
