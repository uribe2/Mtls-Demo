from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import Optional, List
from pymongo import MongoClient
from bson.objectid import ObjectId
import os

MONGO_URI = "mongodb://172.31.73.109:27017"
INTERNAL_TOKEN = "super-secret-token"  # must match gateway

client = MongoClient(MONGO_URI)
db = client["inventory_db"]
items_col = db["items"]

app = FastAPI(title="Inventory Service")

def verify_internal_token(x_internal_token: str = Header(None)):
    if x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized (missing/invalid token)")

class ItemIn(BaseModel):
    name: str
    sku: str
    quantity: int

class ItemOut(ItemIn):
    id: str

def to_item_out(doc) -> ItemOut:
    return ItemOut(
        id=str(doc["_id"]),
        name=doc["name"],
        sku=doc["sku"],
        quantity=doc["quantity"]
    )

@app.get("/items", response_model=List[ItemOut], dependencies=[Depends(verify_internal_token)])
def list_items():
    return [to_item_out(d) for d in items_col.find()]

@app.post("/items", response_model=ItemOut, dependencies=[Depends(verify_internal_token)])
def create_item(item: ItemIn):
    result = items_col.insert_one(item.dict())
    doc = items_col.find_one({"_id": result.inserted_id})
    return to_item_out(doc)
