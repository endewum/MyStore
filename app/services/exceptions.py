"""Domain level exceptions raised by services and rendered by handlers."""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for expected, user-presentable business errors."""

    default_message = "Something went wrong. Please try again."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message


class NotFoundError(ServiceError):
    default_message = "The requested item no longer exists."


class ValidationError(ServiceError):
    default_message = "That input is not valid."


class PermissionDeniedError(ServiceError):
    default_message = "You are not allowed to perform this action."


class OutOfStockError(ServiceError):
    default_message = "This plan just sold out. Please pick another one."


class InvalidStateTransition(ServiceError):
    default_message = "This action is not allowed for the current order status."

    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(
            f"Cannot move an order from {from_status} to {to_status}."
        )
        self.from_status = from_status
        self.to_status = to_status


class PaymentMethodUnavailable(ServiceError):
    default_message = "This payment method is currently unavailable."


class CouponError(ServiceError):
    default_message = "This coupon cannot be used."
