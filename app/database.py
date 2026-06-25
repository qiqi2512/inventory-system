import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 在本机是 localhost；在 Docker 容器里是db db 是 Docker Compose 中数据库服务的名字
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/inventory")

engine = create_engine(DATABASE_URL)
#autocommit=False：不自动提交  autoflush=False：关闭自动刷新 
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()