from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import (
    TypeVar,
    Generic,
    Protocol,
    Dict,
    List,
    Optional,
    Union,
    Sequence,
    runtime_checkable,
    Any,
    TypedDict,
    Mapping,
    Literal,
    Tuple as PyTuple,
)
from typing_extensions import TypeAlias
from datetime import datetime
from enum import Enum

# Type variables
T = TypeVar("T")
M = TypeVar("M", bound="Match")
C = TypeVar("C", bound="Caveats")
R = TypeVar("R", bound="Resource")
A = TypeVar("A", bound="Ability")

# Basic types
DID = str
Resource = str
Ability = str
URI = str
UCANLink = Any  # Link type from IPLD
Result = Union["Ok[T]", "Error"]


@dataclass
class Source:
    """Source of a capability claim"""

    capability: Dict[str, Any]  # {can, with, nb}
    delegation: "Delegation"


@dataclass
class Match(Generic[T, M]):
    """Match result for capability validation"""

    source: List[Source]
    value: T
    proofs: List["Delegation"]

    def prune(self, config: "CanIssue") -> Optional["Match"]:
        """Prune invalid capability chains"""
        ...


@runtime_checkable
class Matcher(Protocol[M]):
    """Protocol for matching capabilities"""

    @abstractmethod
    def match(self, capability: Source) -> Result[M, "InvalidCapability"]:
        """Match a capability source"""
        ...


@dataclass
class Select(Generic[M]):
    """Selection of matched capabilities"""

    matches: List[M]
    errors: List["DelegationError"]
    unknown: List["Capability"]


@runtime_checkable
class Selector(Protocol[M]):
    """Protocol for selecting capabilities"""

    @abstractmethod
    def select(self, sources: List[Source]) -> Select[M]:
        """Select matching capabilities from sources"""
        ...


@dataclass
class Caveats:
    """Arbitrary capability caveats"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@dataclass
class ParsedCapability(Generic[A, R, C]):
    """Parsed capability with typed components"""

    can: A
    with_: R
    nb: Optional[C] = None


@dataclass
class DirectMatch(Match[T, "DirectMatch[T]"]):
    """Direct capability match"""

    pass


@dataclass
class DerivedMatch(Match[T, Union[M, "DerivedMatch[T, M]"]]):
    """Match derived from another capability"""

    pass


@dataclass
class Capability:
    """Raw capability data"""

    can: Ability
    with_: Resource
    nb: Optional[Dict[str, Any]] = None


class CapabilityParser(Protocol[M]):
    """Protocol for parsing and validating capabilities"""

    @abstractmethod
    def parse(self, capability: Capability) -> Result[M, "InvalidCapability"]:
        """Parse raw capability"""
        ...

    @abstractmethod
    def or_(self, other: "MatchSelector[M]") -> "CapabilityParser[M]":
        """Combine with another capability parser"""
        ...

    @abstractmethod
    def and_(self, other: "MatchSelector[M]") -> "CapabilitiesParser[M]":
        """Group with another capability"""
        ...

    @abstractmethod
    def derive(self, options: Dict[str, Any]) -> "CapabilityParser[DerivedMatch]":
        """Define derived capability"""
        ...


@runtime_checkable
class CapabilitiesParser(Protocol[M]):
    """Protocol for parsing multiple capabilities"""

    @abstractmethod
    def parse(
        self, capabilities: List[Capability]
    ) -> Result[List[M], List["InvalidCapability"]]:
        """Parse multiple capabilities"""
        ...

    @abstractmethod
    def and_(self, other: "MatchSelector[M]") -> "CapabilitiesParser[M]":
        """Add capability to group"""
        ...


# Validation errors
@dataclass
class Failure(Exception):
    """Base class for validation failures"""

    message: str


@dataclass
class InvalidCapability(Failure):
    """Error for invalid capability format/content"""

    name: Literal["UnknownCapability", "MalformedCapability"]
    capability: Capability


@dataclass
class DelegationError(Failure):
    """Error in delegation chain"""

    name: Literal["InvalidClaim"]
    causes: List[Union["InvalidCapability", "EscalatedDelegation", "DelegationError"]]
    cause: Union["InvalidCapability", "EscalatedDelegation", "DelegationError"]


@dataclass
class EscalatedDelegation(Failure):
    """Error for unauthorized capability escalation"""

    name: Literal["EscalatedCapability"]
    claimed: ParsedCapability
    delegated: object
    cause: Failure


@dataclass
class InvalidAudience(Failure):
    """Error for wrong delegation audience"""

    name: Literal["InvalidAudience"]


@dataclass
class Unauthorized(Failure):
    """Error for unauthorized capability use"""

    name: Literal["Unauthorized"]
    delegation_errors: List[DelegationError]
    unknown_capabilities: List[Capability]
    invalid_proofs: List["InvalidProof"]
    failed_proofs: List["InvalidClaim"]


# Validation interfaces
@runtime_checkable
class CanIssue(Protocol):
    """Protocol for checking capability issuance authority"""

    @abstractmethod
    def can_issue(self, capability: ParsedCapability, issuer: DID) -> bool:
        """Check if issuer can issue capability"""
        ...


@runtime_checkable
class ProofResolver(Protocol):
    """Protocol for resolving delegation proofs"""

    @abstractmethod
    async def resolve(
        self, proof: UCANLink
    ) -> Result["Delegation", "UnavailableProof"]:
        """Resolve proof by link"""
        ...


@runtime_checkable
class Validator(Protocol):
    """Protocol for validating capabilities"""

    @abstractmethod
    async def validate(
        self,
        capability: ParsedCapability,
        delegation: "Delegation",
        options: "ValidationOptions",
    ) -> Result["Authorization", "Unauthorized"]:
        """Validate delegated capability"""
        ...


@dataclass
class ValidationOptions:
    """Options for capability validation"""

    capability: CapabilityParser
    authority: "Verifier"
    principal: "PrincipalParser"
    can_issue: Optional[CanIssue] = None
    resolver: Optional[ProofResolver] = None


@dataclass
class Authorization:
    """Authorized capability with proof chain"""

    delegation: "Delegation"
    capability: ParsedCapability
    proofs: List["Authorization"]
    issuer: "Principal"
    audience: "Principal"
