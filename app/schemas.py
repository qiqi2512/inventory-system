from pydantic import BaseModel, ConfigDict, Field

# schemas.py: API 的请求/响应数据结构。可以选择性暴露字段，修改数据库不影响 API 格式。

# POST /reserve 预占请求
class ReserveRequest(BaseModel):
    order_no: str = Field(min_length=1, description="订单号，不能为空")
    sku: str = Field(min_length=1, description="商品 SKU")
    # gt=0：数量必须大于 0。传 0 或负数会被 FastAPI 自动拦截，返回 422，根本进不到业务层
    quantity: int = Field(gt=0, description="预占数量，必须为正整数")


# /release 和 /confirm：释放/确认只需要订单号
class ActionRequest(BaseModel):
    order_no: str = Field(min_length=1)


# 查询库存返回结构
class InventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    available: int
    reserved: int


# 返回订单信息
class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_no: str
    sku: str
    quantity: int
    status: str
