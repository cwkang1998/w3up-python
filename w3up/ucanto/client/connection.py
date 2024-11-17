from typing import Sequence, List
from core.interfaces.base import ConnectionOptions


# TODO: missing a lot of imports, fix those
class Connection:
    def __init__(self, options: ConnectionOptions) -> None:
        self.id = options.id
        self.options = options
        self.codec = options.codec
        self.channel = options.channel
        self.hasher = options.hasher

    def execute(self, invocations: Sequence["ServiceInvocation"]) -> List["Receipt"]:
        # Build message with invocations
        input_msg = Message.build({"invocations": invocations})

        # Encode and send request
        request = self.codec.encode(input_msg, connection)
        response = self.channel.request(request)

        # Attempt to decode response
        try:
            output = self.codec.decode(response)
            receipts = [output.get(link) for link in input_msg.invocation_links]
            return receipts

        except Exception as error:
            # Create error receipts if decode fails
            receipts = []

            # Extract error details
            error_dict = {
                "message": str(error),
                "name": error.__class__.__name__,
                **{
                    k: v
                    for k, v in asdict(error).items()
                    if k not in ["message", "name"]
                },
            }

            # Create error receipt for each invocation
            for ran in input_msg.invocation_links:
                # Create dummy signer
                dummy_signer = DummySigner(
                    did=lambda: self.id.did(),
                    sign=lambda: Signature.create_non_standard("", bytes()),
                )

                # Issue error receipt
                receipt = Receipt.issue(
                    ran=ran, result={"error": error_dict}, issuer=dummy_signer
                )

                receipts.append(receipt)

            return receipts
