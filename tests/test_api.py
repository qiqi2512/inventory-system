"""接口验证用例。

为什么用 SQLite 内存库而不是 Postgres：
- 测试要能在任何机器上「一条命令跑起来」，不依赖 Docker / 真实数据库。
- 业务逻辑（状态机、库存加减、数量校验、防重）与具体数据库无关。
- `with_for_update()` 是并发悲观锁，SQLite 不支持时 SQLAlchemy 会自动忽略，不影响这些功能性断言。

并发防超卖属于「真 Postgres 行级锁」的能力，需要并发压测验证，不在本单元测试范围内，已在 README 说明。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app import models
from app.main import app
from app.routes import get_db


@pytest.fixture()
def client():
    """每个测试一个全新的内存数据库，保证用例之间互不影响。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 同一个内存连接，建表和请求共用，否则内存库会各自为政
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)

    # 初始化和生产一致的基础数据：SKU001 available=10, reserved=0
    db = TestingSessionLocal()
    db.add(models.Inventory(sku="SKU001", available=10, reserved=0))
    db.commit()
    db.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # 用测试数据库替换真实数据库依赖；不进入 lifespan（即不连 Postgres）
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# 1. 查询初始库存
def test_initial_inventory(client):
    resp = client.get("/inventory/SKU001")
    assert resp.status_code == 200
    assert resp.json() == {"sku": "SKU001", "available": 10, "reserved": 0}


# 2. 成功预占 2 件
def test_reserve_success(client):
    resp = client.post("/reserve", json={"order_no": "O1", "sku": "SKU001", "quantity": 2})
    assert resp.status_code == 201
    assert resp.json()["status"] == "RESERVED"

    inv = client.get("/inventory/SKU001").json()
    assert inv == {"sku": "SKU001", "available": 8, "reserved": 2}


# 3. 库存不足时失败
def test_reserve_insufficient(client):
    resp = client.post("/reserve", json={"order_no": "O1", "sku": "SKU001", "quantity": 100})
    assert resp.status_code == 400
    assert "Insufficient" in resp.json()["detail"]
    # 失败后库存不应被改动
    assert client.get("/inventory/SKU001").json()["available"] == 10


# 4. 释放订单：库存恢复
def test_release_restores_inventory(client):
    client.post("/reserve", json={"order_no": "O1", "sku": "SKU001", "quantity": 3})
    resp = client.post("/release", json={"order_no": "O1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "RELEASED"

    inv = client.get("/inventory/SKU001").json()
    assert inv == {"sku": "SKU001", "available": 10, "reserved": 0}


# 5. 确认订单：available 不回补，reserved 清掉
def test_confirm_order(client):
    client.post("/reserve", json={"order_no": "O1", "sku": "SKU001", "quantity": 4})
    resp = client.post("/confirm", json={"order_no": "O1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "CONFIRMED"

    inv = client.get("/inventory/SKU001").json()
    assert inv == {"sku": "SKU001", "available": 6, "reserved": 0}


# 6a. 非法状态：不能重复释放
def test_cannot_release_twice(client):
    client.post("/reserve", json={"order_no": "O1", "sku": "SKU001", "quantity": 2})
    client.post("/release", json={"order_no": "O1"})
    resp = client.post("/release", json={"order_no": "O1"})
    assert resp.status_code == 400


# 6b. 非法状态：确认后不能再释放
def test_cannot_release_after_confirm(client):
    client.post("/reserve", json={"order_no": "O1", "sku": "SKU001", "quantity": 2})
    client.post("/confirm", json={"order_no": "O1"})
    resp = client.post("/release", json={"order_no": "O1"})
    assert resp.status_code == 400


# 6c. 非法状态：不能重复确认
def test_cannot_confirm_twice(client):
    client.post("/reserve", json={"order_no": "O1", "sku": "SKU001", "quantity": 2})
    client.post("/confirm", json={"order_no": "O1"})
    resp = client.post("/confirm", json={"order_no": "O1"})
    assert resp.status_code == 400


# 7. 负数 / 0 数量不能提交（Pydantic 校验，返回 422）
@pytest.mark.parametrize("bad_qty", [-1, 0])
def test_invalid_quantity_rejected(client, bad_qty):
    resp = client.post("/reserve", json={"order_no": "O1", "sku": "SKU001", "quantity": bad_qty})
    assert resp.status_code == 422
    # 非法请求不应改动库存
    assert client.get("/inventory/SKU001").json()["available"] == 10


# 额外：重复 order_no 返回清晰的 409，而不是 500
def test_duplicate_order_no(client):
    first = client.post("/reserve", json={"order_no": "O1", "sku": "SKU001", "quantity": 2})
    assert first.status_code == 201
    dup = client.post("/reserve", json={"order_no": "O1", "sku": "SKU001", "quantity": 1})
    assert dup.status_code == 409
    # 第二次失败不应再扣库存
    assert client.get("/inventory/SKU001").json() == {"sku": "SKU001", "available": 8, "reserved": 2}
