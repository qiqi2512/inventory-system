from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import schemas, service

router = APIRouter()

# 每个请求自动获取并关闭数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/inventory/{sku}", response_model=schemas.InventoryResponse)
def read_inventory(sku: str, db: Session = Depends(get_db)):
    return service.get_inventory(db, sku)


@router.post("/reserve", response_model=schemas.OrderResponse, status_code=201)
def reserve(req: schemas.ReserveRequest, db: Session = Depends(get_db)):
    return service.reserve_inventory(db, req)


@router.post("/release", response_model=schemas.OrderResponse)
def release(req: schemas.ActionRequest, db: Session = Depends(get_db)):
    return service.release_inventory(db, req)


@router.post("/confirm", response_model=schemas.OrderResponse)
def confirm(req: schemas.ActionRequest, db: Session = Depends(get_db)):
    return service.confirm_inventory(db, req)


@router.get("/orders/{order_no}", response_model=schemas.OrderResponse)
def read_order(order_no: str, db: Session = Depends(get_db)):
    return service.get_order(db, order_no)