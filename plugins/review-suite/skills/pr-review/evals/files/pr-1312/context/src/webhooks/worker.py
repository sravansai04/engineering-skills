# Consumes the "webhooks" queue.
#
# A message is acked only after handle() returns. An unacked message becomes
# visible again after VISIBILITY_TIMEOUT seconds and is redelivered to any free
# worker, so delivery is at-least-once. Each worker process handles one message
# at a time.
from webhooks.deliver import deliver

VISIBILITY_TIMEOUT = 30  # seconds


def handle(message, db):
    deliver(message["delivery_id"], db)
    message.ack()
