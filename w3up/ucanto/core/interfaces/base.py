from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import (
    Any, TypeVar, Generic, Dict, List, Set, Union, Optional, 
    Protocol, runtime_checkable, Tuple, Type, Iterator,
    TypedDict, Literal, Callable, Mapping, NewType
)
from datetime import datetime
import asyncio
from enum import Enum
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from multiformats import CID, multicodec, multihash, multibase

# Type variables
T = TypeVar('T')
I = TypeVar('I')
O = TypeVar('O')
C = TypeVar('C', bound='Capabilities')
X = TypeVar('X', bound=Exception)

# Basic types
DID = NewType('DID', str)  # did:method:specific
Resource = NewType('Resource', str)  
Ability = NewType('Ability', str)
Nonce = NewType('Nonce', str)
UTCUnixTimestamp = NewType('UTCUnixTimestamp', int)

class SignatureAlgorithm(Enum):
    """Supported signature algorithms"""
    Ed25519 = 'Ed25519'
    Secp256k1 = 'Secp256k1'
    RSA = 'RSA'

@dataclass
class ByteView(Generic[T]):
    """Represents byte encoded data"""
    bytes: bytes
    encoding: str

@dataclass
class SignatureView:
    """View of a cryptographic signature"""
    bytes: bytes
    algorithm: SignatureAlgorithm

@dataclass 
class Block(Generic[T]):
    """IPLD block with encoded data"""
    cid: CID
    bytes: bytes
    value: T

@dataclass
class Fact:
    """Arbitrary facts that can be included in a UCAN"""
    uri: str
    data: Any

class Principal(Protocol):
    """Interface for UCAN principals (issuers/audiences)"""
    @abstractmethod
    def did(self) -> str:
        """Returns DID of the principal"""
        ...
        
@dataclass
class Capability:
    """Represents a UCAN capability"""
    with_: Resource  # Resource identifier
    can: Ability    # Action that can be performed
    nb: Optional[Dict[str, Any]] = None  # Caveats

@dataclass
class UCANOptions:
    """Base options for UCAN creation"""
    audience: Principal
    lifetime_in_seconds: Optional[int] = None
    expiration: Optional[UTCUnixTimestamp] = None
    not_before: Optional[UTCUnixTimestamp] = None 
    nonce: Optional[Nonce] = None
    facts: Optional[List[Fact]] = None
    proofs: Optional[List['Proof']] = None
    attached_blocks: Optional[Dict[str, Block]] = None

@dataclass
class DelegationOptions(UCANOptions):
    """Options for delegating capabilities"""
    issuer: 'Signer'
    capabilities: List[Capability]

class IPLDView(Protocol[T]):
    """Interface for IPLD DAG views"""
    @property
    @abstractmethod
    def root(self) -> Block[T]:
        """Root block of the DAG"""
        ...

    @abstractmethod
    def iterate_ipld_blocks(self) -> Iterator[Block]:
        """Iterate through all blocks in the DAG"""
        ...

@runtime_checkable
class Delegation(IPLDView[T], Protocol[T]):
    """Interface for UCAN delegations"""
    cid: CID
    bytes: ByteView
    data: Any
    issuer: Principal  
    audience: Principal
    capabilities: List[Capability]
    expiration: UTCUnixTimestamp
    not_before: Optional[UTCUnixTimestamp]
    nonce: Optional[Nonce]
    facts: List[Fact]
    proofs: List['Proof']
    signature: SignatureView

    @abstractmethod
    def as_cid(self) -> CID:
        """Get delegation as CID"""
        ...

    @abstractmethod
    def delegate(self) -> 'Delegation':
        """Create a new delegation"""
        ...

class Signer(Protocol):
    """Interface for UCAN issuers"""
    @abstractmethod
    def did(self) -> str:
        """Get DID of the signer"""
        ...

    @abstractmethod
    async def sign(self, data: bytes) -> SignatureView:
        """Sign arbitrary bytes"""
        ...

    @abstractmethod 
    def verify(self, data: bytes, signature: SignatureView) -> bool:
        """Verify a signature"""
        ...

@dataclass
class ValidatorOptions:
    """Options for UCAN validation"""
    principal_parser: Optional['PrincipalParser'] = None
    can_issue: Optional[Callable[..., bool]] = None
    resolve: Optional[Callable[..., 'Delegation']] = None

    @abstractmethod
    def validate_authorization(self, proofs: List['Authorization']) -> bool:
        """Validate authorization chain"""
        ...

# Result types        
@dataclass
class Ok(Generic[T]):
    """Successful result"""
    value: T

@dataclass 
class Error(Generic[X], Exception):
    """Error result"""
    error: X

Result = Union[Ok[T], Error[X]]

# Receipt types
@dataclass
class ReceiptModel(Generic[T, X]):
    """Model for capability invocation receipts"""
    outcome: 'OutcomeModel[T, X]'
    signature: SignatureView

@dataclass
class OutcomeModel(Generic[T, X]):
    """Model for invocation outcomes"""
    ran: CID  # Invocation CID
    output: Result[T, X]
    effects: 'EffectsModel'
    meta: Dict[str, Any]
    issuer: Optional[DID] = None
    proofs: List[CID] = None

@dataclass
class EffectsModel:
    """Model for capability effects"""
    fork: List[CID]  # Links to forked invocations
    join: Optional[CID] = None  # Link to joined invocation

# Transport types
class HTTPError(Exception):
    """HTTP transport error"""
    def __init__(self, status: int, message: Optional[str] = None):
        self.status = status
        self.message = message
        super().__init__(message or f"HTTP {status}")

class InboundCodec(Protocol):
    """Interface for inbound message codec"""
    @abstractmethod
    def accept(self, request: Any) -> Result['InboundAcceptCodec', HTTPError]:
        """Accept and decode inbound request"""
        ...

class OutboundCodec(Protocol):
    """Interface for outbound message codec"""
    @abstractmethod
    def encode_request(self, data: Any) -> bytes:
        """Encode outbound request"""
        ...

    @abstractmethod
    def decode_response(self, data: bytes) -> Any:
        """Decode inbound response""" 
        ...

@dataclass
class ConnectionOptions:
    """Options for UCAN connections"""
    id: Principal
    codec: OutboundCodec
    channel: Any  # Transport channel

class PrincipalParser(Protocol):
    """Interface for parsing principals from DIDs"""
    @abstractmethod
    def parse(self, did: str) -> 'Verifier':
        """Parse DID into verifier"""
        ...

class Verifier(Protocol):
    """Interface for UCAN verification"""
    @abstractmethod
    def verify(self, data: bytes, signature: SignatureView) -> bool:
        """Verify signature"""
        ...
```

This Python implementation provides:

1. Core UCAN Types:
   - DID identifiers and resources
   - Capabilities and delegations
   - Cryptographic primitives (signatures, principals)
   - IPLD data structures

2. Key Interfaces:
   - `Principal` - For UCAN actors
   - `Signer` - For issuing UCANs
   - `Verifier` - For verifying UCANs
   - `Delegation` - For capability delegation

3. Transport and Codec Types:
   - HTTP transport errors
   - Inbound/outbound message codecs
   - Connection management

4. Result Types:
   - Generic Ok/Error results
   - Receipt and outcome models
   - Effect tracking

Usage example:

```python
async def delegate_capability(
    issuer: Signer,
    audience: Principal,
    capability: Capability
) -> Delegation:
    """Delegate a capability to another principal"""
    
    options = DelegationOptions(
        issuer=issuer,
        audience=audience,
        capabilities=[capability],
        expiration=int(datetime.now().timestamp()) + 3600,
    )
    
    delegation = await create_delegation(options)
    return delegation

async def verify_delegation(
    delegation: Delegation,
    validator: ValidatorOptions
) -> bool:
    """Verify a capability delegation"""
    
    # Verify signature
    valid_sig = delegation.issuer.verify(
        delegation.bytes.bytes,
        delegation.signature
    )
    
    if not valid_sig:
        return False
        
    # Validate authorization chain
    valid_auth = await validator.validate_authorization(delegation.proofs)
    
    return valid_auth
