from payments.client import PaymentError


def is_retryable(error: Exception) -> bool:
    return isinstance(error, PaymentError) and error.retryable
