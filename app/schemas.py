from pydantic import BaseModel

#schemas.py API的请求/响应数据结构 可以选择性暴露字段 修改数据库不影响 API 格式

#post/reserve  预占请求
class ReserveRequest(BaseModel):
    order_no: str
    sku: str
    quantity: int

#/release 和 /confirm  释放确认只需要知道订单号
class ActionRequest(BaseModel):
    order_no: str

#查询库存返回结构
class InventoryResponse(BaseModel):
    sku: str
    available: int
    reserved: int

    class Config:
        from_attributes = True

#返回订单信息
class OrderResponse(BaseModel):
    order_no: str
    sku: str
    quantity: int
    status: str

    class Config:
        from_attributes = True