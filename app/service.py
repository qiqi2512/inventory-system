from sqlalchemy.orm import Session
from fastapi import HTTPException
from app import models, schemas

#service.py 核心业务逻辑

def reserve_inventory(db: Session, req: schemas.ReserveRequest):
    # 1. 查询库存并锁定，防止并发修改 
    # SELECT * FROM inventory WHERE sku = req.sku
    #with_for_update()  悲观锁在查询库存时，这条 SQL 会锁定查到的行，直到当前事务结束
    inventory = db.query(models.Inventory).filter(
        models.Inventory.sku == req.sku
    ).with_for_update().first()

    if not inventory:
        raise HTTPException(status_code=404, detail="SKU not found")
    if inventory.available < req.quantity:
        raise HTTPException(status_code=400, detail="Insufficient inventory")

    # 2. 扣减可售库存，增加预占库存  还未写入数据库 只有commit之后才写
    inventory.available -= req.quantity
    inventory.reserved += req.quantity

    # 3. 创建订单，状态直接设为 RESERVED 锁定
    order = models.Order(
        order_no=req.order_no,
        sku=req.sku,
        quantity=req.quantity,
        status="RESERVED"
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def release_inventory(db: Session, req: schemas.ActionRequest):
    # 1. 查询订单并锁定
    order = db.query(models.Order).filter(
        models.Order.order_no == req.order_no
    ).with_for_update().first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "RESERVED":
        raise HTTPException(status_code=400, detail="Order status is not RESERVED, cannot release")

    # 2. 恢复库存并锁定库存行
    inventory = db.query(models.Inventory).filter(
        models.Inventory.sku == order.sku
    ).with_for_update().first()

    inventory.available += order.quantity
    inventory.reserved -= order.quantity

    # 3. 更新订单状态
    order.status = "RELEASED"
    db.commit()
    db.refresh(order)
    return order


def confirm_inventory(db: Session, req: schemas.ActionRequest):
    order = db.query(models.Order).filter(
        models.Order.order_no == req.order_no
    ).with_for_update().first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "RESERVED":
        raise HTTPException(status_code=400, detail="Order status is not RESERVED, cannot confirm")

    # 只减少预占库存，available 不变（因为已经卖出去了）
    inventory = db.query(models.Inventory).filter(
        models.Inventory.sku == order.sku
    ).with_for_update().first()

    inventory.reserved -= order.quantity
    order.status = "CONFIRMED"

    db.commit()
    db.refresh(order)
    return order


def get_inventory(db: Session, sku: str):
    inv = db.query(models.Inventory).filter(models.Inventory.sku == sku).first()
    if not inv:
        raise HTTPException(status_code=404, detail="SKU not found")
    return inv


def get_order(db: Session, order_no: str):
    order = db.query(models.Order).filter(models.Order.order_no == order_no).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order