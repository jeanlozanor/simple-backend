from sqlalchemy import Column, Integer, ForeignKey, Numeric, String, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from db import Base

class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="PEN")
    stock = Column(Integer, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", backref="inventory_items")
    product = relationship("Product", backref="inventory_items")
