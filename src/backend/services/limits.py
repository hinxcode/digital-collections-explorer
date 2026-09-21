import asyncio
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from typing import Deque, Optional

from fastapi import HTTPException, Request, UploadFile

from ..core.site_settings import site_settings

WINDOW_SECONDS = 60
MAX_TRACKED_VISITORS = 10_000
QUEUE_SECONDS = 15
UPLOAD_CHUNK_BYTES = 1024 * 1024
# Bytes of form fields and boundaries that surround the image in an upload.
UPLOAD_FORM_OVERHEAD_BYTES = 64 * 1024
MAX_UPLOAD_PIXELS = 50_000_000


def visitor_address(request: Request) -> str:
    """The visitor's address, read past the proxies the administrator has declared"""
    hops = site_settings()["proxy_hops"]
    forwarded = [
        part.strip()
        for part in request.headers.get("x-forwarded-for", "").split(",")
        if part.strip()
    ]
    if hops and len(forwarded) >= hops:
        return forwarded[-hops]
    return request.client.host if request.client else "unknown"


class SearchAllowance:
    def __init__(self):
        self.recent: "OrderedDict[str, Deque[float]]" = OrderedDict()

    def seconds_until_allowed(
        self, visitor: str, per_minute: int, now: Optional[float] = None
    ) -> int:
        """Record one search, or say how long this visitor has to wait"""
        if not per_minute:
            return 0
        now = time.monotonic() if now is None else now
        times = self.recent.setdefault(visitor, deque())
        self.recent.move_to_end(visitor)
        while times and now - times[0] >= WINDOW_SECONDS:
            times.popleft()
        if len(times) >= per_minute:
            return max(1, int(WINDOW_SECONDS - (now - times[0])) + 1)
        times.append(now)
        while len(self.recent) > MAX_TRACKED_VISITORS:
            self.recent.popitem(last=False)
        return 0


allowance = SearchAllowance()


async def limit_searches(request: Request) -> None:
    wait = allowance.seconds_until_allowed(
        visitor_address(request), site_settings()["searches_per_minute"]
    )
    if wait:
        raise HTTPException(
            status_code=429,
            detail="You are searching very quickly. Please wait a moment and try again.",
            headers={"Retry-After": str(wait)},
        )


class SearchQueue:
    def __init__(self):
        self.slots: Optional[asyncio.Semaphore] = None
        self.size = 0

    @asynccontextmanager
    async def turn(self):
        """Let only a few searches use the model at once, and turn the rest away"""
        size = max(1, site_settings()["concurrent_searches"])
        if size != self.size:
            self.slots, self.size = asyncio.Semaphore(size), size
        slots = self.slots
        try:
            await asyncio.wait_for(slots.acquire(), timeout=QUEUE_SECONDS)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=503,
                detail="The site is busy right now. Please try again in a moment.",
                headers={"Retry-After": str(QUEUE_SECONDS)},
            )
        try:
            yield
        finally:
            slots.release()


search_queue = SearchQueue()


async def read_upload(upload: UploadFile) -> bytes:
    """Read an uploaded file, giving up as soon as it passes the size limit"""
    limit_mb = site_settings()["max_upload_mb"]
    limit = limit_mb * 1024 * 1024
    chunks, size = [], 0
    while True:
        chunk = await upload.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if limit and size > limit:
            raise HTTPException(
                status_code=413,
                detail=f"That image is too large. Please use one under {limit_mb} MB.",
            )
        chunks.append(chunk)


def refuse_oversized_upload(request: Request) -> None:
    """Turn an upload away from its headers alone, before any of it is stored"""
    if request.method != "POST":
        return
    limit_mb = site_settings()["max_upload_mb"]
    if not limit_mb:
        return
    declared = request.headers.get("content-length", "")
    if not declared.isdigit():
        raise HTTPException(
            status_code=411, detail="The upload must say how large it is."
        )
    if int(declared) > limit_mb * 1024 * 1024 + UPLOAD_FORM_OVERHEAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"That image is too large. Please use one under {limit_mb} MB.",
        )
