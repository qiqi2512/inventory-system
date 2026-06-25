from fastapi import FastAPI
from app.database import engine, Base
import app.models               # 确保模型类被加载，这样 Base.metadata 才知道有哪些表
from app.routes import router   # 导入我们写好的路由

# 如果表还没创建，就自动创建（已存在则跳过）
Base.metadata.create_all(bind=engine)

app = FastAPI()

# 把 routes.py 里的所有接口注册到主应用上
app.include_router(router)