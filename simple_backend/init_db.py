#!/usr/bin/env python3
"""
Script para inicializar la base de datos con tiendas de prueba
"""
import os
from sqlalchemy import create_engine
from db import Base, SessionLocal, DATABASE_URL
from models import Store

# Eliminar DB anterior
db_path = "simple.db"
if os.path.exists(db_path):
    os.remove(db_path)
    print(f"✓ Base de datos anterior eliminada")

# Recrear tablas
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(bind=engine)
print("✓ Tablas creadas")

# Insertar tiendas
db = SessionLocal()

stores = [
    Store(
        name="Hiraoka Miraflores",
        code="hiraoka-miraflores",
        address="Av. Larco 1234",
        district="Miraflores",
        city="Lima",
        latitude=-12.1265,
        longitude=-77.0296,
        payment_methods="tarjeta,efectivo,yape,plin"
    ),
    Store(
        name="Hiraoka San Isidro",
        code="hiraoka-san-isidro",
        address="Av. Paseo de la República 3456",
        district="San Isidro",
        city="Lima",
        latitude=-12.0904,
        longitude=-77.0360,
        payment_methods="tarjeta,efectivo,yape,plin"
    ),
    Store(
        name="Falabella Miraflores",
        code="falabella-miraflores",
        address="Av. Larco 5678",
        district="Miraflores",
        city="Lima",
        latitude=-12.1275,
        longitude=-77.0306,
        payment_methods="tarjeta,efectivo,yape"
    ),
    Store(
        name="Falabella Centro",
        code="falabella-centro",
        address="Jr. Carabaya 789",
        district="Lima Cercado",
        city="Lima",
        latitude=-12.0459,
        longitude=-77.0318,
        payment_methods="tarjeta,efectivo"
    ),
    Store(
        name="Alkosto Online",
        code="alkosto-online",
        address=None,
        district=None,
        city="Online",
        latitude=-12.06,
        longitude=-77.04,
        payment_methods="tarjeta"
    ),
    Store(
        name="Promart",
        code="promart",
        address=None,
        district=None,
        city="Online",
        latitude=-12.06,
        longitude=-77.04,
        payment_methods="tarjeta,efectivo"
    ),
    Store(
        name="Oechsle",
        code="oechsle",
        address=None,
        district=None,
        city="Online",
        latitude=-12.06,
        longitude=-77.04,
        payment_methods="tarjeta,efectivo"
    ),
    Store(
        name="PlazaVea",
        code="plazavea",
        address=None,
        district=None,
        city="Online",
        latitude=-12.06,
        longitude=-77.04,
        payment_methods="tarjeta,efectivo"
    ),
]

for store in stores:
    db.add(store)
    print(f"✓ Tienda creada: {store.name} ({store.code})")

db.commit()
db.close()

print(f"\n✓ Total tiendas insertadas: {len(stores)}")
print("Base de datos inicializada correctamente!")
