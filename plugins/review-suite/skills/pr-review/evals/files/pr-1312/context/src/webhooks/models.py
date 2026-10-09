from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from webhooks.db import Base


class Delivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(BigInteger, primary_key=True)
    endpoint_id = Column(ForeignKey("webhook_endpoints.id"), nullable=False)
    endpoint = relationship("Endpoint")
    payload_json = Column(Text, nullable=False)
    # pending -> delivered | failed. Only "failed" rows are picked up by jobs/redrive.py.
    status = Column(String, nullable=False, default="pending")
    # Number of HTTP POSTs made for this delivery. Shown on the customer's delivery log page.
    attempts = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
