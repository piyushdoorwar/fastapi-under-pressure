from sqlalchemy import ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(
        String(20), primary_key=True
    )
    name: Mapped[str]
    price_cents: Mapped[int]
    weight_grams: Mapped[int]
    stock_levels: Mapped[list["StockLevel"]] = (
        relationship(
            back_populates="product",
            order_by="StockLevel.warehouse",
        )
    )


class StockLevel(Base):
    __tablename__ = "stock_levels"

    sku: Mapped[str] = mapped_column(
        ForeignKey("products.sku"), primary_key=True
    )
    warehouse: Mapped[str] = mapped_column(
        String(20), primary_key=True
    )
    qty: Mapped[int]
    product: Mapped[Product] = relationship(
        back_populates="stock_levels"
    )
