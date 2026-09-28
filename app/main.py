"""
FastAPI app: serves the chat frontend and the /api/analyze endpoint that
wires Agent 1 (extraction) and Agent 2 (matching + calculation) together.

Run locally with:
    uvicorn app.main:app --reload

Deployable as a single web service (e.g. to Render) -- see README for hosting.
"""

import logging
import os

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .agent1_extraction import run_agent1, to_agent2_input
from .agent2_matching import MatchingError, run_agent2
from .chat_formatter import build_chat_response

logger = logging.getLogger("sailor_health_app")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Sailor Health Claim Denial Triage Tool")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/about")
def serve_about():
    return FileResponse(os.path.join(STATIC_DIR, "about.html"))


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    reference = file.filename or "uploaded document"

    try:
        extraction = run_agent1(pdf_bytes)
    except RuntimeError as e:
        return JSONResponse(
            status_code=500,
            content={
                "valid": False,
                "message": "This tool is temporarily unavailable (server configuration issue), not a problem with your file. Please try again shortly.",
                "detail": str(e),
            },
        )
    except Exception as e:  # noqa: BLE001 -- e.g. an Anthropic API error (rate limit, bad PDF bytes, etc.)
        logger.exception("Agent 1 failed unexpectedly")
        return JSONResponse(
            status_code=500,
            content={
                "valid": False,
                "message": "Something went wrong while reading this file. Please try again.",
                "detail": str(e),
            },
        )

    if not extraction.get("valid"):
        return JSONResponse(
            content={
                "valid": False,
                "message": "Unrecognized format -- please upload a claim denial notice in a recognized format.",
                "detail": extraction.get("reason"),
            }
        )

    agent2_input = to_agent2_input(extraction)
    try:
        agent2_output = run_agent2(agent2_input)
    except MatchingError as e:
        return JSONResponse(
            content={
                "valid": False,
                "message": "This claim could not be matched against the historical dataset.",
                "detail": str(e),
            }
        )
    except Exception as e:  # noqa: BLE001 -- last-resort guard so a bug surfaces a clean message, not a raw 500
        logger.exception("Agent 2 failed unexpectedly")
        return JSONResponse(
            status_code=500,
            content={
                "valid": False,
                "message": "Something went wrong while calculating the recommendation. Please try again.",
                "detail": str(e),
            },
        )

    chat = build_chat_response(agent2_output, reference=reference)
    chat["valid"] = True
    chat["extraction"] = extraction  # full raw extraction, useful for the UI/debugging
    return JSONResponse(content=chat)


# Mount static assets (css/js) last so the explicit routes above take priority.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
