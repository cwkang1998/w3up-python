from abc import ABC
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Union, Iterable
from urllib.parse import URL
import asyncio
from enum import Enum
import json

# Type aliases
DID = str
EmailAddress = str
SpaceDID = str
ServiceAbility = str
Capability = Dict[str, Any]
Principal = Any  # Principal interface implementation
Delegation = Any  # UCAN Delegation type
UnknownLink = bytes  # Multiformats CID type
BlobLike = Union[bytes, bytearray, "Blob"]  # File-like objects
FileLike = Union[str, bytes, "File"]  # File-like objects


@dataclass
class ServiceConf:
    """Service configuration for web3.storage"""

    upload: str
    store: str


@dataclass
class UploadOptions:
    """Options for upload operations"""

    name: Optional[str] = None
    signal: Optional[asyncio.Event] = None
    onShardStored: Optional[callable] = None
    connection: Optional[str] = None


@dataclass
class UploadFileOptions(UploadOptions):
    """Options specific to file uploads"""

    pass


@dataclass
class UploadDirectoryOptions(UploadOptions):
    """Options specific to directory uploads"""

    pass


@dataclass
class AgentMeta:
    """Metadata about an agent"""

    name: str
    type: str


class Base:
    """Base class for Web3.Storage client functionality"""

    def __init__(self, agent_data: dict, options: Optional[dict] = None):
        self._agent = agent_data
        self._service_conf = options.get("serviceConf") if options else None
        self._receipts_endpoint = options.get("receiptsEndpoint") if options else None

    async def _invocation_config(self, capabilities: List[str]) -> dict:
        """Generate config for capability invocation"""
        return {
            "issuer": self._agent,
            "with": self.currentSpace().did() if self.currentSpace() else None,
            "proofs": self.proofs(capabilities),
        }


class Client(Base):
    """Main Web3.Storage client implementation"""

    def __init__(self, agent_data: dict, options: Optional[dict] = None):
        super().__init__(agent_data, options)

        # Initialize capability clients
        self.capability = {
            "access": AccessClient(agent_data, options),
            "filecoin": FilecoinClient(agent_data, options),
            "index": IndexClient(agent_data, options),
            "plan": PlanClient(agent_data, options),
            "space": SpaceClient(agent_data, options),
            "blob": BlobClient(agent_data, options),
            "store": StoreClient(agent_data, options),
            "subscription": SubscriptionClient(agent_data, options),
            "upload": UploadClient(agent_data, options),
            "usage": UsageClient(agent_data, options),
        }

        self.coupon = CouponAPI(agent_data, options)

    def did(self) -> str:
        """Get the DID of the agent"""
        return self._agent.did()

    async def authorize(
        self, email: EmailAddress, options: Optional[dict] = None
    ) -> None:
        """Authorize agent to use capabilities granted to email account"""
        await self.capability["access"].authorize(email, options or {})

    async def login(self, email: EmailAddress, options: dict = {}) -> "Account":
        """Log in with email address"""
        account = Result.unwrap(await Account.login(self, email, options))
        Result.unwrap(await account.save())
        return account

    def accounts(self) -> Dict[str, "Account"]:
        """List accessible accounts"""
        return Account.list(self)

    async def upload_file(
        self, file: BlobLike, options: Optional[UploadFileOptions] = None
    ) -> UnknownLink:
        """Upload a single file"""
        conf = await self._invocation_config(
            ["space/blob/add", "space/index/add", "filecoin/offer", "upload/add"]
        )

        if options:
            options.connection = self._service_conf.upload

        return await upload_file(conf, file, options or UploadFileOptions())

    async def upload_directory(
        self, files: List[FileLike], options: Optional[UploadDirectoryOptions] = None
    ) -> UnknownLink:
        """Upload a directory of files"""
        conf = await self._invocation_config(
            ["space/blob/add", "space/index/add", "filecoin/offer", "upload/add"]
        )

        if options:
            options.connection = self._service_conf.upload

        return await upload_directory(conf, files, options or UploadDirectoryOptions())

    async def upload_car(
        self, car: BlobLike, options: Optional[UploadOptions] = None
    ) -> UnknownLink:
        """Upload a CAR file"""
        conf = await self._invocation_config(
            ["space/blob/add", "space/index/add", "filecoin/offer", "upload/add"]
        )

        if options:
            options.connection = self._service_conf.upload

        return await upload_car(conf, car, options or UploadOptions())

    async def get_receipt(self, task_cid: UnknownLink) -> dict:
        """Get receipt for completed task"""
        receipts_endpoint = str(URL(self._receipts_endpoint))
        return await Receipt.poll(task_cid, {"receiptsEndpoint": receipts_endpoint})

    def default_provider(self) -> str:
        """Get default provider DID"""
        return self._agent.connection.id.did()

    def current_space(self) -> Optional["Space"]:
        """Get current space"""
        agent = self._agent
        space_id = agent.current_space()
        if not space_id:
            return None
        meta = agent.spaces.get(space_id)
        return Space(id=space_id, meta=meta, agent=agent)

    async def set_current_space(self, did: DID) -> None:
        """Set current space"""
        await self._agent.set_current_space(did)

    def spaces(self) -> List["Space"]:
        """Get all available spaces"""
        return [
            Space(id=id_, meta=meta, agent=self._agent)
            for id_, meta in self._agent.spaces.items()
        ]

    async def create_space(self, name: str, options: dict = {}) -> "OwnedSpace":
        """Create a new space"""
        space = await self._agent.create_space(name)

        account = options.get("account")
        if account:
            # Provision account with space
            provision_result = await account.provision(space.did())
            if provision_result.error:
                raise Exception(
                    f"Failed to provision account: {provision_result.error.message}"
                ) from provision_result.error

            # Save space authorization
            await space.save()

            # Create recovery
            recovery = await space.create_recovery(account.did())

            # Delegate access
            result = await self.capability["access"].delegate(
                {"space": space.did(), "delegations": [recovery]}
            )

            if result.error:
                raise Exception(
                    f"Failed to authorize recovery account: {result.error.message}"
                ) from result.error

        return space

    async def share_space(
        self, delegate_email: EmailAddress, space_did: SpaceDID, options: dict = None
    ) -> "AgentDelegation":
        """Share space with another account"""
        if options is None:
            options = {
                "abilities": [
                    "space/*",
                    "store/*",
                    "upload/*",
                    "access/*",
                    "usage/*",
                    "filecoin/offer",
                    "filecoin/info",
                    "filecoin/accept",
                    "filecoin/submit",
                ],
                "expiration": float("inf"),
            }

        abilities = options.get("abilities", [])
        current_space = self.agent.current_space()

        try:
            # Set space context
            await self.agent.set_current_space(space_did)

            # Create delegation
            delegation_data = await self.agent.delegate(
                {
                    **options,
                    "abilities": abilities,
                    "audience": {
                        "did": lambda: DIDMailto.from_email(
                            DIDMailto.email(delegate_email)
                        )
                    },
                    "audienceMeta": options.get("audienceMeta", {}),
                }
            )

            delegation = AgentDelegation(
                delegation_data["root"],
                delegation_data["blocks"],
                {"audience": delegate_email},
            )

            # Share space
            share_result = await self.capability["access"].delegate(
                {"space": space_did, "delegations": [delegation]}
            )

            if share_result.error:
                raise Exception(
                    f"Failed to share space with {delegate_email}: {share_result.error.message}"
                ) from share_result.error

            return delegation

        finally:
            # Restore original space
            if current_space and current_space != space_did:
                await self.agent.set_current_space(current_space)

    async def add_space(self, proof: Delegation) -> None:
        """Add space from proof"""
        return await self._agent.import_space_from_delegation(proof)

    def proofs(self, caps: Optional[List[Capability]] = None) -> List[Delegation]:
        """Get matching capability proofs"""
        return self._agent.proofs(caps)

    async def add_proof(self, proof: Delegation) -> None:
        """Add a capability proof"""
        await self._agent.add_proof(proof)

    def delegations(
        self, caps: Optional[List[Capability]] = None
    ) -> List["AgentDelegation"]:
        """Get delegations created by agent"""
        return [
            AgentDelegation(d.delegation.root, d.delegation.blocks, d.meta)
            for d in self._agent.delegations_with_meta(caps)
        ]

    async def create_delegation(
        self, audience: Principal, abilities: List[ServiceAbility], options: dict = None
    ) -> "AgentDelegation":
        """Create new delegation"""
        options = options or {}
        audience_meta = options.get("audienceMeta", {"name": "agent", "type": "device"})

        delegation_data = await self._agent.delegate(
            {
                **options,
                "abilities": abilities,
                "audience": audience,
                "audienceMeta": audience_meta,
            }
        )

        return AgentDelegation(
            delegation_data["root"],
            delegation_data["blocks"],
            {"audience": audience_meta},
        )

    async def revoke_delegation(
        self, delegation_cid: bytes, options: dict = None
    ) -> None:
        """Revoke a delegation"""
        return await self._agent.revoke(
            delegation_cid, {"proofs": options.get("proofs") if options else None}
        )

    async def remove(self, content_cid: UnknownLink, options: dict = None) -> None:
        """Remove content and optionally its shards"""
        options = options or {}

        # Just remove content association if not removing shards
        if not options.get("shards"):
            await self.capability["upload"].remove(content_cid)
            return

        # Get and remove shards
        upload = await self.capability["upload"].get(content_cid)
        if upload.get("shards"):
            await asyncio.gather(
                *[self._remove_shard(shard) for shard in upload["shards"]]
            )

        # Remove content association
        await self.capability["upload"].remove(content_cid)

    async def _remove_shard(self, shard: dict) -> None:
        """Helper to remove a single shard"""
        try:
            result = await self.capability["blob"].remove(shard["multihash"])

            # Try store removal if blob not found
            if result.get("ok", {}).get("size") == 0:
                await self.capability["store"].remove(shard)

        except Exception as e:
            # Ignore not found errors
            if (
                getattr(e, "cause", None)
                and getattr(e.cause, "name") != "StoreItemNotFound"
            ):
                raise Exception(f"Failed to remove shard: {shard}") from e


# Helper classes and functions would be implemented here:
# - Receipt
# - Space
# - OwnedSpace
# - Account
# - AgentDelegation
# - Result
# - Various capability clients
