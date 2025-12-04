from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from pymongo import MongoClient
import requests

#  Replenishment DB (CHANGE THIS IP)
MONGO_URI = "mongodb://172.31.68.145:27017"  # <-- your rep-db private IP

client = MongoClient(MONGO_URI)
db = client["replenishment_db"]
orders_col = db["orders"]

#  Gateway mTLS settings
GATEWAY_URL = "https://gateway.local:8443"
CERT = (
    "/etc/replenishment/certs/replenishment-client.crt",
    "/etc/replenishment/certs/replenishment-client.key",
)
CA = "/etc/replenishment/certs/demo-root.crt"
THRESHOLD = 10

app = FastAPI(title="Replenishment Service")


# ---- Models -----------------------------------------------------------------
class Order(BaseModel):
    id: str
    item_id: str
    sku: str
    quantity_to_order: int


# ---- Helpers ----------------------------------------------------------------
def fetch_inventory_items():
    """Call Inventory via gateway+mTLS and return JSON list of items."""
    r = requests.get(f"{GATEWAY_URL}/inventory/items", cert=CERT, verify=CA)
    r.raise_for_status()
    return r.json()


def doc_to_order(doc) -> Order:
    """Convert a MongoDB document into an Order model with string id."""
    return Order(
        id=str(doc["_id"]),
        item_id=str(doc["item_id"]),
        sku=doc["sku"],
        quantity_to_order=int(doc["quantity_to_order"]),
    )


def create_order(item: dict) -> Order:
    """Insert a new order in Mongo and return it as an Order."""
    qty_to_order = THRESHOLD - int(item["quantity"])
    doc = {
        "item_id": item["id"],            # inventory id is already a string
        "sku": item["sku"],
        "quantity_to_order": qty_to_order,
    }
    result = orders_col.insert_one(doc)
    # re-fetch so we have the _id and any future fields
    saved = orders_col.find_one({"_id": result.inserted_id})
    return doc_to_order(saved)


# ---- Endpoints --------------------------------------------------------------
@app.post("/run-check")
def run_check():
    """
    Fetch inventory items via mTLS, create orders for any below THRESHOLD.
    """
    items = fetch_inventory_items()
    low = [i for i in items if int(i["quantity"]) < THRESHOLD]
    created = [create_order(i) for i in low]

    # created is a list of Order models, which FastAPI can encode just fine
    return {"created_orders": created}


@app.get("/orders", response_model=List[Order])
def list_orders():
    docs = list(orders_col.find())
    return [doc_to_order(d) for d in docs]

@app.delete("/orders")
def delete_all_orders():
    """
    Delete ALL replenishment orders from MongoDB.
    Use for resetting the demo.
    """
    result = orders_col.delete_many({})
    return {"deleted_count": result.deleted_count}
