import os
import time
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base

# 在本机是 localhost；在 Docker 容器里是 db（db 是 docker-compose 中数据库服务的名字）
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/inventory")

# pool_pre_ping=True：每次从连接池取连接前先 ping 一下，避免拿到失效连接
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# autocommit=False：不自动提交；autoflush=False：关闭自动刷新
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def wait_for_db(max_retries: int = 30, delay: float = 2.0) -> None:
    """等待数据库可连接。

    docker compose 启动时，即使 db 容器已起来，PostgreSQL 进程也可能还没完成初始化。
    这里主动重试，连接成功才返回，避免 app 因为「连了一个还没 ready 的库」而秒退。
    """
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[startup] 数据库连接成功（第 {attempt} 次尝试）")
            return
        except OperationalError as err:
            last_err = err
            print(f"[startup] 数据库还没就绪，{delay}s 后重试（{attempt}/{max_retries}）")
            time.sleep(delay)
    raise RuntimeError(f"数据库在 {max_retries} 次重试后仍不可用") from last_err
