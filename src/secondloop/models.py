from sqlalchemy import String
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(
        String(20), primary_key=True
    )
    name: Mapped[str]
    price_cents: Mapped[int]
    weight_grams: Mapped[int]
    stock: Mapped[int]
