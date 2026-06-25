# 库存预占系统

## 1. 设计思路
- 采用 库存表 (inventory) 和 订单表 (orders) 分离的设计：库存表是当前状态记录可售库存 (`available`) 和已预占库存 (`reserved`)，订单表是历史日志记录每次预占的明细及状态。通过订单表，可以追踪任何一次库存变更的来源。
- 订单从创建到完结有严格的状态机：只能从 RESERVED 转为 CONFIRMED 或 RELEASED，其他任何跳转都会被业务层拦截返回 400 错误。
- 业务逻辑全部放在 service.py，路由只做转发放在 routes.py，数据模型用 models.py 和 schemas.py 分开，每一层各干各的，改数据库不影响接口格式。每个请求通过 FastAPI 的依赖注入自动获取和释放数据库会话，避免资源泄露。
- 所有库存变更操作均在数据库事务中完成，并使用FOR UPDATE并发下不会超卖、库存不会变成负数。

## 2. 状态流转设计

状态图：
CREATED（可选） → RESERVED → CONFIRMED
                    └───→ RELEASED

- `POST /reserve` 成功后订单进入 **RESERVED** 状态，同时预占库存。
- `POST /confirm` 将订单从 **RESERVED** 转为 **CONFIRMED**，表示真正售出。
- `POST /release` 将订单从 **RESERVED** 转为 **RELEASED**，恢复库存。
- 任何从其他状态发起的转换都会被拒绝，返回 **400** 错误。

---

## 3. 库存为什么不会出现负数？

- **行级锁**：对同一 SKU 的库存操作使用 `SELECT ... FOR UPDATE`，并发请求会串行执行。
- **事务内校验**：在锁保护下判断 `available >= quantity`，不满足则立即拒绝。
- **统一的扣减与恢复逻辑**：
  - 预占时：`available -= quantity`，`reserved += quantity`
  - 确认时：只减少 `reserved`（因为 available 已在预占时扣减）
  - 释放时：`available += quantity`，`reserved -= quantity`
- 所有操作在同一事务中原子完成，不会出现中间不一致状态。


## 4. 使用的 AI 工具

- ChatGPT （代码生成、调试、概念解释）
- Cursor（AI 辅助编辑器）
- 官方文档 + 搜索引擎（FastAPI、SQLAlchemy、PostgreSQL 文档）


## 5. AI 帮我完成了哪些工作

- 生成初始的 FastAPI + SQLAlchemy 项目框架
- 解释 Python 虚拟环境、SQLAlchemy ORM、异步与同步的区别等陌生概念
- 协助编写并解释 `with_for_update()` 防超卖的并发控制代码
- 调试数据库连接错误、Docker 配置问题、端口冲突等
- 起草 README 文档结构与面试可能追问的要点

---

## 6. AI 给过哪些错误答案？你是如何发现并修正的？

1. **初始数据缺失导致接口返回 404**  
   AI 告诉我 `Base.metadata.create_all` 会自动建表和初始化数据。启动服务后查询库存一直报 "SKU not found"。  
     我用 `docker exec` 进入 PostgreSQL 手动查表，发现表建好了但数据是空的。然后自己写了插入语句，把 SKU001 的初始库存加进去，问题解决。  

2. **Docker Compose 构建因网络问题失败**  
   执行 `docker compose up --build` 时，拉取 `python:3.11-slim` 镜像超时。AI 给的方案是改 DNS、重启 Docker，但都不管用。  
    解决方法：数据库继续用 Docker 跑（本地已有 postgres 镜像），应用直接用 `uvicorn` 在本机启动。功能完全一样，而且 Docker 配置文件都保留在项目里，证明我理解容器化部署的逻辑。  


## 运行方式

### 方式一：Docker Compose 一键启动

如果 Docker 能正常拉取镜像，项目根目录下直接执行：

docker compose up --build

等待构建完成后，访问 http://localhost:8000/docs 即可测试。

### 方式二：本地 Python + Docker 数据库混合运行

如果 Docker 构建镜像因网络原因失败，可以采用以下替代方案（效果完全相同）：

1. 启动 PostgreSQL 数据库容器（本地已缓存 postgres 镜像）：
   docker run -d --name inventory-db \
     -e POSTGRES_PASSWORD=postgres \
     -e POSTGRES_USER=postgres \
     -e POSTGRES_DB=inventory \
     -p 5432:5432 postgres:16

2. 安装 Python 依赖：
   pip install -r requirements.txt

3. 初始化库存数据：
   python -c "
   from app.database import SessionLocal
   from app.models import Inventory
   db = SessionLocal()
   db.add(Inventory(sku='SKU001', available=10, reserved=0))
   db.commit()
   db.close()
   "

4. 启动应用：
   uvicorn app.main:app --reload

5. 访问 http://localhost:8000/docs
