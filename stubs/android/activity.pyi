from typing import Any

class Activity:
    RESULT_OK: int

def bind(*args: Any, **kwargs: Any) -> None: ...
def unbind(*args: Any, **kwargs: Any) -> None: ...

activity: Any
