from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine, Base, SessionLocal, wait_for_db
from app import models               # noqa: F401  导入以注册模型，让 Base.metadata 知道有哪些表
from app.routes import router


def seed_initial_data() -> None:
    """初始化基础库存数据，保证服务一启动就能按题目直接测试。

    幂等：SKU001 已存在则跳过，不会重复插入，也不会覆盖已有库存。
    """
    db = SessionLocal()
    try:
        exists = db.query(models.Inventory).filter(models.Inventory.sku == "SKU001").first()
        if exists is None:
            db.add(models.Inventory(sku="SKU001", available=10, reserved=0))
            db.commit()
            print("[startup] 已初始化库存 SKU001: available=10, reserved=0")
        else:
            print("[startup] SKU001 已存在，跳过初始化")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动阶段：先等数据库 ready，再建表、灌初始数据
    wait_for_db()
    Base.metadata.create_all(bind=engine)
    seed_initial_data()
    yield
    # 关闭阶段：本项目没有需要清理的资源


app = FastAPI(title="库存预占系统", lifespan=lifespan)

# 注册 routes.py 里的所有接口
app.include_router(router)


@app.get("/health")
def health():
    """健康检查接口，方便确认服务已正常启动。"""
    return {"status": "ok"}
