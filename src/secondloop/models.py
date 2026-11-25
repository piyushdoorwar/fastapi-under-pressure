from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Sequence,
    String,
    func,
)
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
            lazy="raise_on_sql",
        )
    )


class StockLevel(Base):
    __tablename__ = "stock_levels"
    __table_args__ = (
        CheckConstraint(
            "qty >= 0", name="stock_not_negative"
        ),
    )

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


ORDER_NUMBERS = Sequence(
    "order_numbers", start=10040, metadata=Base.metadata
)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(
        String(20), unique=True
    )
    email: Mapped[str]
    postcode: Mapped[str]
    subtotal_cents: Mapped[int]
    shipping_cents: Mapped[int]
    total_cents: Mapped[int]
    shipping_estimated: Mapped[bool] = mapped_column(
        default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )
    confirmation_sent_at: Mapped[datetime | None]
    lines: Mapped[list["OrderLine"]] = relationship(
        lazy="raise_on_sql"
    )


class OrderLine(Base):
    __tablename__ = "order_lines"

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"), primary_key=True
    )
    sku: Mapped[str] = mapped_column(
        ForeignKey("products.sku"), primary_key=True
    )
    warehouse: Mapped[str] = mapped_column(String(20))
    qty: Mapped[int]
    price_cents: Mapped[int]


class IdempotencyKey(Base):
    """Which order a client's Idempotency-Key made."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(
        String(100), primary_key=True
    )
    request_hash: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )


class OutboxMessage(Base):
    """An email to send, saved in the same transaction
    as the order it belongs to. The worker sends it."""

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )
    available_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None]
    sent_at: Mapped[datetime | None]
