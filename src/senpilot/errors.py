class AgentError(Exception):
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


class DeliveryUnknown(Exception):
    """The provider may have accepted the request; do not automatically resend."""


class DeliveryRejected(Exception):
    """The provider explicitly rejected this send."""
