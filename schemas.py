"""
Database Schemas for the Fashion E‑commerce app

Each Pydantic model corresponds to a MongoDB collection (lowercased class name).
"""
from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal, Dict

# -----------------------------
# Auth / Users
# -----------------------------
class User(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: EmailStr
    password_hash: str
    role: Literal["user", "admin"] = "user"
    avatar_url: Optional[str] = None
    is_active: bool = True

# -----------------------------
# Catalog
# -----------------------------
class ProductVariant(BaseModel):
    size: Optional[str] = None
    color: Optional[str] = None
    stock: int = 0
    sku: Optional[str] = None

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    category: str
    images: List[str] = []
    variants: List[ProductVariant] = []
    tags: List[str] = []
    rating: float = 0.0
    rating_count: int = 0
    is_active: bool = True

# -----------------------------
# Orders / Checkout
# -----------------------------
class CartItem(BaseModel):
    product_id: str
    quantity: int = Field(..., ge=1)
    price: float = Field(..., ge=0)
    title: Optional[str] = None
    variant: Optional[Dict[str, str]] = None  # size/color
    image: Optional[str] = None

class Address(BaseModel):
    full_name: str
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str = "US"
    phone: Optional[str] = None

class Order(BaseModel):
    user_id: Optional[str] = None
    items: List[CartItem]
    subtotal: float = Field(..., ge=0)
    shipping: float = 0.0
    total: float = Field(..., ge=0)
    status: Literal["pending", "paid", "shipped", "delivered", "cancelled"] = "pending"
    payment_method: Literal["stripe", "cod"]
    payment_status: Literal["pending", "requires_action", "paid", "failed"] = "pending"
    transaction_id: Optional[str] = None
    shipping_address: Address
    email: Optional[EmailStr] = None

# Note: The schema viewer in the studio can inspect these on /schema
