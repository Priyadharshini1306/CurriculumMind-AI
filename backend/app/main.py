import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired
from pymongo.errors import PyMongoError
from fastapi.middleware.cors import CORSMiddleware

from app.api import adaptive, auth, courses, dashboard, concepts, curriculum, graph, learner, learning_path, quiz, resources, sequencing, upload
from app.core import mongo, neo4j
from app.core.config import get_settings
from app.services import embedding_service
from app.services.embedding_service import EmbeddingError
from app.services.llm_service import LLMError

log = logging.getLogger("curriculummind")


KEEPALIVE_SECONDS = 15
WARM_CONNECTIONS = 5  # concurrent pings, so several pooled connections are exercised, not just one


async def _keepalive() -> None:
    """The network drops idle database connections, and reconnecting to Atlas/Aura costs seconds. Touching a few pooled
    connections regularly keeps them warm so users do not pay for it."""
    from app.repositories.neo4j_repository import ping
    while True:
        await asyncio.sleep(KEEPALIVE_SECONDS)
        try:
            await asyncio.gather(*[mongo.get_db().command("ping") for _ in range(WARM_CONNECTIONS)],
                                 *[ping() for _ in range(WARM_CONNECTIONS)], return_exceptions=True)
        except Exception:  # best effort only
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    secret = get_settings().jwt_secret
    if len(secret) < 32:
        log.error("JWT_SECRET is missing or shorter than 32 characters: logins will fail or be insecure")
    try:
        await mongo.init_indexes()
    except Exception as e:
        log.warning("MongoDB not ready: %s", e)
    try:
        from app.repositories.neo4j_repository import init_schema
        await init_schema()
    except Exception as e:
        log.warning("Neo4j not ready: %s", e)
    keepalive = asyncio.create_task(_keepalive())
    warmup = asyncio.create_task(embedding_service.warmup())  # in the background: the API serves requests meanwhile
    yield
    keepalive.cancel()
    warmup.cancel()
    await mongo.close()
    await neo4j.close()


app = FastAPI(title="CurriculumMind AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
def _problem(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message})


@app.exception_handler(PyMongoError)
async def mongo_error(_: Request, exc: PyMongoError):
    log.error("MongoDB error: %s", exc)
    return _problem(503, "The user database (MongoDB) is temporarily unavailable. Please retry.")


@app.exception_handler(Neo4jError)
@app.exception_handler(ServiceUnavailable)
@app.exception_handler(SessionExpired)
async def neo4j_error(_: Request, exc: Exception):
    log.error("Neo4j error: %s", exc)
    return _problem(503, "The knowledge-graph database (Neo4j) is temporarily unavailable. Please retry.")


@app.exception_handler(LLMError)
async def llm_error(_: Request, exc: LLMError):
    log.error("LLM error: %s", exc)
    return _problem(502, f"The AI model could not complete the request: {exc}")


@app.exception_handler(EmbeddingError)
async def embedding_error(_: Request, exc: EmbeddingError):
    log.error("Embedding error: %s", exc)
    return _problem(503, "The embedding model is unavailable.")


@app.exception_handler(Exception)
async def unexpected(_: Request, exc: Exception):
    log.exception("Unhandled error")  # details stay in the server log, never in the response
    return _problem(500, "Internal server error")


app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(curriculum.router)
app.include_router(concepts.router)
app.include_router(graph.router)
app.include_router(sequencing.router)
app.include_router(resources.router)
app.include_router(learning_path.router)
app.include_router(quiz.router)
app.include_router(learner.router)
app.include_router(adaptive.router)
app.include_router(dashboard.router)
app.include_router(courses.router)


@app.get("/api/health")
async def health():
    status = {"api": "ok", "mongodb": "down", "neo4j": "down"}
    try:
        await mongo.get_db().command("ping")
        status["mongodb"] = "ok"
    except Exception:
        pass
    try:
        from app.repositories.neo4j_repository import ping
        if await ping():
            status["neo4j"] = "ok"
    except Exception:
        pass
    return status
