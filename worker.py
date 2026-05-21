from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import os
import resource
import time

from gomoku import score_move


app = FastAPI()
started_at = time.time()
job_stats = {
    "queued": 0,
    "running": 0,
    "completed": 0,
    "failed": 0,
    "current_job": None,
    "last_job": None,
}


class ScoreRequest(BaseModel):
    board: list[list[str]]
    candidates: list[list[int]]
    job_id: str | None = None


@app.post("/score")
def score_candidates(request: ScoreRequest):
    job_id = request.job_id or f"job-{int(time.time() * 1000)}"
    job_stats["queued"] = max(0, job_stats["queued"] - 1)
    job_stats["running"] += 1
    job_stats["current_job"] = job_id
    started = time.time()
    scores = []

    try:
        for row, col in request.candidates:
            scores.append(
                {
                    "move": [row, col],
                    "score": score_move(request.board, row, col),
                }
            )
    except Exception:
        job_stats["failed"] += 1
        raise
    finally:
        job_stats["running"] = max(0, job_stats["running"] - 1)
        job_stats["current_job"] = None

    job_stats["completed"] += 1
    job_stats["last_job"] = {
        "id": job_id,
        "candidate_count": len(request.candidates),
        "duration_seconds": round(time.time() - started, 3),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    return {"job_id": job_id, "scores": scores}


@app.get("/status")
def status():
    return {
        "pid": os.getpid(),
        "uptime_seconds": round(time.time() - started_at, 1),
        "jobs": job_stats,
        "resources": get_resource_usage(),
    }


def get_resource_usage():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    memory_mb = usage.ru_maxrss / 1024
    if os.uname().sysname == "Darwin":
        memory_mb = usage.ru_maxrss / (1024 * 1024)

    return {
        "process_cpu_seconds": round(usage.ru_utime + usage.ru_stime, 2),
        "process_memory_mb": round(memory_mb, 2),
        "load_average": [round(value, 2) for value in os.getloadavg()],
    }
