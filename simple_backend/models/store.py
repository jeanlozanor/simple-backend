from sqlalchemy import Column, Integer, String, Float
from db import Base

class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    code = Column(String(100), nullable=False, unique=True, index=True)
    address = Column(String(300), nullable=True)
    district = Column(String(100), nullable=True, index=True)
    city = Column(String(100), nullable=True, default="Lima")
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    # Ejemplo: "tarjeta,efectivo,yape"
    payment_methods = Column(String(200), nullable=True)