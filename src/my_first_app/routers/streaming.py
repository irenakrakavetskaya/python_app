from collections.abc import AsyncIterable

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

router = APIRouter()


class StreamItem(BaseModel):
    name: str
    description: str | None


streamItems = [
    StreamItem(name="Plumbus", description="A multi-purpose household device."),
    StreamItem(name="Portal Gun", description="A portal opening device."),
    StreamItem(name="Meeseeks Box", description="A box that summons a Meeseeks."),
]


class Prompt(BaseModel):
    text: str


@router.get("/items/stream", response_class=EventSourceResponse)
async def sse_items() -> AsyncIterable[StreamItem]:
    for item in StreamItem:
        yield item


@router.get("/items/stream-retry", response_class=EventSourceResponse)
async def stream_items() -> AsyncIterable[ServerSentEvent]:
    yield ServerSentEvent(comment="stream of item updates")
    for i, item in enumerate(streamItems):
        yield ServerSentEvent(data=item, event="item_update", id=str(i + 1), retry=5000)


@router.post("/chat/stream", response_class=EventSourceResponse)
async def stream_chat(prompt: Prompt) -> AsyncIterable[ServerSentEvent]:
    words = prompt.text.split()
    for word in words:
        yield ServerSentEvent(data=word, event="token")
    yield ServerSentEvent(raw_data="[DONE]", event="done")
