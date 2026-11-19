"""Synchronous gameplay events delivered on the simulation thread."""
from collections import defaultdict
from collections.abc import Callable

Handler = Callable[..., None]


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> None:
        if handler not in self._listeners[event]:
            self._listeners[event].append(handler)

    def unsubscribe(self, event: str, handler: Handler) -> None:
        listeners = self._listeners.get(event, [])
        if handler in listeners:
            listeners.remove(handler)

    def publish(self, event: str, **payload) -> None:
        for handler in tuple(self._listeners.get(event, ())):
            handler(**payload)
