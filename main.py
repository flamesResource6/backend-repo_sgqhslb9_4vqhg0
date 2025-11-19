import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Product, User, Order

app = FastAPI(title="Fashion Commerce API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ObjectIdStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        try:
            return str(ObjectId(v))
        except Exception:
            raise ValueError("Invalid ObjectId")

# -----------------
# Utility helpers
# -----------------

def to_public(doc: Dict[str, Any]):
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc

@app.get("/")
def root():
    return {"name": "Fashion Commerce API", "status": "ok"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# -----------------
# Auth (basic demo)
# -----------------
class AuthPayload(BaseModel):
    name: Optional[str] = None
    email: str
    password: str

@app.post("/auth/signup")
def signup(payload: AuthPayload):
    # Very naive demo: hash-less storage not recommended; we expect password_hash field
    existing = list(db.user.find({"email": payload.email})) if db else []
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(name=payload.name or payload.email.split("@")[0], email=payload.email, password_hash=payload.password)
    user_id = create_document("user", user)
    return {"id": user_id, "email": user.email, "name": user.name, "role": user.role}

@app.post("/auth/login")
def login(payload: AuthPayload):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    user = db.user.find_one({"email": payload.email, "password_hash": payload.password})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = to_public(user)
    return {"token": user["id"], "user": {"id": user["id"], "email": user["email"], "name": user.get("name"), "role": user.get("role", "user")}}

# -----------------
# Catalog
# -----------------
@app.get("/products")
def list_products(q: Optional[str] = None, category: Optional[str] = None, size: Optional[str] = None, color: Optional[str] = None, min_price: Optional[float] = None, max_price: Optional[float] = None):
    if db is None:
        return []
    query: Dict[str, Any] = {"is_active": True}
    if q:
        query["title"] = {"$regex": q, "$options": "i"}
    if category:
        query["category"] = category
    price_filter = {}
    if min_price is not None:
        price_filter["$gte"] = float(min_price)
    if max_price is not None:
        price_filter["$lte"] = float(max_price)
    if price_filter:
        query["price"] = price_filter
    if size:
        query["variants.size"] = size
    if color:
        query["variants.color"] = color

    docs = list(db.product.find(query).limit(60))
    return [to_public(d) for d in docs]

@app.get("/products/{product_id}")
def get_product(product_id: str):
    if db is None:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        doc = db.product.find_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return to_public(doc)

# -----------------
# Admin (basic)
# -----------------
class ProductIn(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    images: Optional[List[str]] = None
    variants: Optional[List[Dict[str, Any]]] = None
    tags: Optional[List[str]] = None

@app.post("/admin/products")
def admin_create_product(payload: ProductIn):
    product = Product(**payload.model_dump())
    new_id = create_document("product", product)
    return {"id": new_id}

@app.patch("/admin/products/{product_id}")
def admin_update_product(product_id: str, payload: Dict[str, Any]):
    if db is None:
        raise HTTPException(status_code=500, detail="DB not ready")
    try:
        result = db.product.update_one({"_id": ObjectId(product_id)}, {"$set": payload})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"updated": True}

@app.delete("/admin/products/{product_id}")
def admin_delete_product(product_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="DB not ready")
    try:
        result = db.product.delete_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}

# -----------------
# Checkout / Orders
# -----------------
class CheckoutPayload(BaseModel):
    items: List[Dict[str, Any]]
    email: Optional[str] = None
    shipping_address: Dict[str, Any]
    payment_method: str  # stripe or cod

@app.post("/checkout")
def checkout(payload: CheckoutPayload):
    if not payload.items:
        raise HTTPException(status_code=400, detail="No items")
    subtotal = sum(float(i.get("price", 0)) * int(i.get("quantity", 1)) for i in payload.items)
    shipping = 0.0
    total = round(subtotal + shipping, 2)

    order = Order(
        user_id=None,
        items=payload.items,  # validated loosely
        subtotal=subtotal,
        shipping=shipping,
        total=total,
        payment_method=payload.payment_method, 
        shipping_address=payload.shipping_address,
        email=payload.email,
    )
    order_id = create_document("order", order)

    # Stripe integration placeholder: return client secret if needed
    payment = {"method": payload.payment_method}
    if payload.payment_method == "stripe":
        payment["status"] = "requires_action"  # Frontend would confirm payment
        payment["client_secret"] = f"cs_test_{order_id[:8]}"
    else:
        payment["status"] = "pending"

    return {"order_id": order_id, "total": total, "payment": payment}

# -----------------
# Schema Explorer
# -----------------
@app.get("/schema")
def schema():
    return {
        "user": User.model_json_schema(),
        "product": Product.model_json_schema(),
        "order": Order.model_json_schema(),
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
