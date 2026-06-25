from sqlalchemy import Column, Integer, String
from app.database import Base

#models.py 定义数据库内部表结构

#创建inventory(库存)表
class Inventory(Base):
    __tablename__ = "inventory"

    #string->varchar Integer整数 primary_key主键  nullable 可为空  default=0  如果未插入 reserved值，默认为0
    sku = Column(String, primary_key=True)
    available = Column(Integer, nullable=False)
    reserved = Column(Integer, nullable=False, default=0)

#创建Order(订单)表
class Order(Base):
    __tablename__ = "orders"

    #若是整数和主键的时候autoincrement为true 即为自增id  unique=True  唯一性 order_no
    id = Column(Integer, primary_key=True, index=True)
    order_no = Column(String, unique=True, nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False)