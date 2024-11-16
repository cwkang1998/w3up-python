from typing import Dict, Any
import json


class Failure(Exception):
    """
    Custom exception class implementing the Failure interface.
    """

    @property
    def message(self) -> str:
        """Returns the failure message."""
        return self.__str__()

    def to_json(self) -> Dict[str, str]:
        """
        Returns a JSON-serializable representation of the failure.
        """
        return json.dumps(
            {
                "name": self.__class__.__name__,
                "message": self.message,
                "stack": getattr(self, "__traceback__", None).__str__(),
            }
        )


def ok(value: Any) -> Dict[str, Any]:
    """
    Creates a success result containing the given value.
    """
    if value is None:
        raise TypeError(f"ok({value}) is not allowed, consider ok({{}}) instead")
    return {"ok": value}


def error(cause: Any) -> Dict[str, Any]:
    """
    Creates a failing result containing the given cause of error.
    """
    if cause is None:
        raise TypeError(
            f"error({cause}) is not allowed, consider passing an error instead"
        )
    return {"error": cause}


def panic(message: str) -> None:
    """
    Crashes the program with a given message.
    """
    raise Failure(message)


def fail(message: str) -> Dict[str, Failure]:
    return {"error": Failure(message)}
