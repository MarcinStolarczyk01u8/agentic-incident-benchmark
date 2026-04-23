from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.sql import func
from app.database import Base

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    product_name = Column(String(255))
    quantity = Column(Integer)
    total_price = Column(Float)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, server_default=func.now())
