from dataclasses import dataclass


class BaseSchema:
    def __init__(self, settings) -> None:
        self.settings = settings

    def read_with(self, input_value: I, settings: Settings) -> Result:
        """Validate input with settings"""
        pass

    def read(self, input_value: I) -> Result:
        """Validate input value"""
        return self.read_with(input_value, self.settings)

    def is_valid(self, value: Any) -> bool:
        """Check if value matches schema"""
        result = self.read(value)
        return result.error is None

    def from_value(self, value: Any) -> T:
        """Convert value to schema type"""
        result = self.read(value)
        if result.error:
            raise result.error
        return result.ok

    def optional(self) -> "Optional_[T, I]":
        """Make schema optional"""
        return Optional_(self)

    def nullable(self) -> "Nullable[T, I]":
        """Make schema nullable"""
        return Nullable(self)

    def array(self) -> "ArrayOf[T, I]":
        """Create array schema"""
        return ArrayOf(self)


@dataclass
class Result:
    """Represents a validation result"""

    ok: Optional[Any] = None
    error: Optional["SchemaError"] = None


class SchemaError(Exception):
    """Base class for schema validation errors"""

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(self.message)

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def describe(self) -> str:
        return self.message


class API(ABC, Generic[T, I, Settings]):
    """Base class for all schema validators"""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings

    def __str__(self) -> str:
        return f"new {self.__class__.__name__}()"

    @abstractmethod
    def read_with(self, input_value: I, settings: Settings) -> Result:
        """Validate input with settings"""
        pass

    def read(self, input_value: I) -> Result:
        """Validate input value"""
        return self.read_with(input_value, self.settings)

    def is_valid(self, value: Any) -> bool:
        """Check if value matches schema"""
        result = self.read(value)
        return result.error is None

    def from_value(self, value: Any) -> T:
        """Convert value to schema type"""
        result = self.read(value)
        if result.error:
            raise result.error
        return result.ok

    def optional(self) -> "Optional_[T, I]":
        """Make schema optional"""
        return Optional_(self)

    def nullable(self) -> "Nullable[T, I]":
        """Make schema nullable"""
        return Nullable(self)

    def array(self) -> "ArrayOf[T, I]":
        """Create array schema"""
        return ArrayOf(self)


class Never(API[None, I, None]):
    """Schema that never matches"""

    def read_with(self, input_value: I, settings: None) -> Result:
        return Result(error=TypeError_("never", input_value))

    def __str__(self) -> str:
        return "never()"


class Unknown(API[Any, I, None]):
    """Schema that matches anything"""

    def read_with(self, input_value: I, settings: None) -> Result:
        return Result(ok=input_value)

    def __str__(self) -> str:
        return "unknown()"


class Nullable(API[Optional[O], I, API[O, I, Any]]):
    """Schema for nullable values"""

    def read_with(self, input_value: I, reader: API[O, I, Any]) -> Result:
        if input_value is None:
            return Result(ok=None)
        result = reader.read(input_value)
        if result.error:
            return Result(
                error=UnionError([result.error, TypeError_("null", input_value)])
            )
        return result

    def __str__(self) -> str:
        return f"{self.settings}.nullable()"


class Optional_(API[Optional[O], I, API[O, I, Any]]):
    """Schema for optional values"""

    def read_with(self, input_value: I, reader: API[O, I, Any]) -> Result:
        if input_value is None:
            return Result(ok=None)
        result = reader.read(input_value)
        return Result(ok=None) if result.error and input_value is None else result

    def __str__(self) -> str:
        return f"{self.settings}.optional()"


class ArrayOf(API[List[O], I, API[O, I, Any]]):
    """Schema for arrays"""

    def read_with(self, input_value: I, schema: API[O, I, Any]) -> Result:
        if not isinstance(input_value, list):
            return Result(error=TypeError_("array", input_value))

        results = []
        for index, value in enumerate(input_value):
            result = schema.read(value)
            if result.error:
                return Result(error=ElementError(index, result.error))
            results.append(result.ok)
        return Result(ok=results)

    @property
    def element(self):
        return self.settings

    def __str__(self) -> str:
        return f"array({self.element})"


class Dictionary(API[Dict[str, V], I, Dict[str, Any]]):
    """Schema for dictionary objects"""

    def read_with(self, input_value: I, settings: Dict[str, Any]) -> Result:
        if not isinstance(input_value, dict):
            return Result(error=TypeError_("dictionary", input_value))

        result = {}
        for key, value in input_value.items():
            key_result = settings["key"].read(key)
            if key_result.error:
                return Result(error=FieldError(key, key_result.error))

            value_result = settings["value"].read(value)
            if value_result.error:
                return Result(error=FieldError(key, value_result.error))

            if value_result.ok is not None:
                result[key_result.ok] = value_result.ok

        return Result(ok=result)

    def __str__(self) -> str:
        return f"dictionary({self.settings})"


class TypeError_(SchemaError):
    """Type mismatch error"""

    def __init__(self, expect: str, actual: Any):
        self.expect = expect
        self.actual = actual
        super().__init__(
            f"Expected value of type {expect} instead got {to_string(actual)}"
        )


class UnionError(SchemaError):
    """Union type mismatch error"""

    def __init__(self, causes: List[SchemaError]):
        self.causes = causes
        messages = "\n".join(f"  - {cause.message}" for cause in causes)
        super().__init__(f"Value does not match any type of the union:\n{messages}")


class ElementError(SchemaError):
    """Array element error"""

    def __init__(self, index: int, cause: SchemaError):
        self.index = index
        self.cause = cause
        super().__init__(
            f"Array contains invalid element at {index}:\n  - {cause.message}"
        )


class FieldError(SchemaError):
    """Dictionary field error"""

    def __init__(self, key: str, cause: SchemaError):
        self.key = key
        self.cause = cause
        super().__init__(f"Object contains invalid field '{key}':\n  - {cause.message}")


def to_string(value: Any) -> str:
    """Convert value to string representation"""
    if value is None:
        return "null"
    elif isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, list):
        return "array"
    elif isinstance(value, dict):
        return "object"
    else:
        return type(value).__name__


# Factory functions
def never() -> Never:
    return Never()


def unknown() -> Unknown:
    return Unknown()


def nullable(schema: API[O, I, Any]) -> Nullable[O, I]:
    return Nullable(schema)


def optional(schema: API[O, I, Any]) -> Optional_[O, I]:
    return Optional_(schema)


def array(schema: API[O, I, Any]) -> ArrayOf[O, I]:
    return ArrayOf(schema)


def dictionary(
    value_schema: API[V, I, Any], key_schema: Optional[API[str, str, Any]] = None
) -> Dictionary[V, I]:
    return Dictionary({"value": value_schema, "key": key_schema or String()})


# Basic type schemas
class String(API[str, Any, None]):
    """String schema validator"""

    def read_with(self, input_value: Any, settings: None) -> Result:
        if isinstance(input_value, str):
            return Result(ok=input_value)
        return Result(error=TypeError_("string", input_value))


class Number(API[float, Any, None]):
    """Number schema validator"""

    def read_with(self, input_value: Any, settings: None) -> Result:
        if isinstance(input_value, (int, float)):
            return Result(ok=float(input_value))
        return Result(error=TypeError_("number", input_value))


class Boolean(API[bool, Any, None]):
    """Boolean schema validator"""

    def read_with(self, input_value: Any, settings: None) -> Result:
        if isinstance(input_value, bool):
            return Result(ok=input_value)
        return Result(error=TypeError_("boolean", input_value))


class Integer(API[int, Any, None]):
    """Integer schema validator"""

    def read_with(self, input_value: Any, settings: None) -> Result:
        if isinstance(input_value, int):
            return Result(ok=input_value)
        return Result(error=TypeError_("integer", input_value))


# Factory functions for basic types
def string() -> String:
    return String()


def number() -> Number:
    return Number()


def boolean() -> Boolean:
    return Boolean()


def integer() -> Integer:
    return Integer()
