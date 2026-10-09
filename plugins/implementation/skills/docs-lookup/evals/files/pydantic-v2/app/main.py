import logging

from fastapi import FastAPI

from app.models import CreateOrder

log = logging.getLogger("orders")
app = FastAPI()


@app.post("/orders")
def create_order(body: CreateOrder) -> dict:
    # TODO: structured log of the request body
    return {"status": "accepted"}
