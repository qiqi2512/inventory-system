# 库存预占系统

基于 FastAPI + PostgreSQL 的库存预占（reserve / release / confirm）服务。

---

## 快速开始（一条命令）

```bash
docker compose up --build
```

启动后访问 http://localhost:8000/docs 即可测试。服务启动时会**自动建表并初始化** `SKU001`（available=10, reserved=0），无需任何手动操作。

### 运行测试

方式一：在 Docker 里一键跑（不用本机装 Python）：

```bash
docker compose run --rm test
```

方式二：本机直接跑（用 SQLite 内存库，不依赖 Docker）：

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

方式三：针对已运行服务的端到端冒烟脚本（先 docker compose up，再另开终端执行）：

```bash
bash verify.sh
```

---

## 一、接口说明

| 方法 | 路径 | 说明 | 成功码 |
|------|------|------|--------|
| GET  | `/inventory/{sku}` | 查询库存 | 200 |
| POST | `/reserve` | 预占库存，创建订单 | 201 |
| POST | `/release` | 释放预占，恢复库存 | 200 |
| POST | `/confirm` | 确认订单，真正售出 | 200 |
| GET  | `/orders/{order_no}` | 查询订单 | 200 |
| GET  | `/health` | 健康检查 | 200 |

请求示例：

```bash
curl -X POST http://localhost:8000/reserve \
  -H 'Content-Type: application/json' \
  -d '{"order_no":"ORD-1","sku":"SKU001","quantity":2}'
```

错误码约定：

| 场景 | 状态码 |
|------|--------|
| SKU / 订单不存在 | 404 |
| 库存不足 / 非法状态流转 | 400 |
| 重复 order_no | 409 |
| quantity ≤ 0 等参数非法 | 422 |

---

## 二、设计思路

- **库存表（inventory）与订单表（orders）分离**：库存表记录当前可售库存 `available` 和已预占库存 `reserved`；订单表是历史日志，记录每次预占的明细及状态，可追踪任何一次库存变更的来源。
- **分层**：业务逻辑全部在 `service.py`，路由 `routes.py` 只做转发，模型 `models.py`（数据库表）与 `schemas.py`（API 结构）分离，改数据库不影响接口格式。每个请求通过依赖注入获取并自动释放数据库会话。
- **事务 + 行级锁**：所有库存变更在数据库事务中完成，并用 `SELECT ... FOR UPDATE` 锁定库存行，并发下不会超卖、库存不会变负。

---

## 三、状态流转设计（为什么用简化状态机）

```
RESERVED ──→ CONFIRMED
   └──────→ RELEASED
```

- `POST /reserve` 成功后订单直接进入 **RESERVED**，同时预占库存。
- `POST /confirm` 将订单从 RESERVED 转为 **CONFIRMED**（真正售出）。
- `POST /release` 将订单从 RESERVED 转为 **RELEASED**（恢复库存）。
- 任何从非 RESERVED 状态发起的转换都会被拒绝，返回 **400**。

**为什么没有单独的 CREATED 状态？**
题目的核心是「预占」这一动作。在本系统里，「下单」和「占用库存」是同一个原子操作——一个订单一旦被创建，就必然已经占用了库存，不存在「已创建但还没占库存」的中间态。因此把 CREATED 和 RESERVED 合并，让"创建订单"直接落在 RESERVED，既符合业务语义，也避免了一个永远一闪而过、没有实际副作用的空状态。

如果未来出现「先占购物车名额、稍后再真正扣减库存」这类需求，CREATED 才有独立存在的意义，届时只需在 `reserve` 前增加一个 `create` 接口即可平滑扩展。

---

## 四、库存为什么不会出现负数？

- **行级锁**：对同一 SKU 用 `SELECT ... FOR UPDATE`，并发请求串行执行。
- **事务内校验**：在锁保护下判断 `available >= quantity`，不满足立即拒绝。
- **参数层校验**：`quantity` 必须 `> 0`（Pydantic `Field(gt=0)`），负数/0 在进入业务层之前就被拦截，杜绝「负数把库存反向加回去」。
- **统一加减逻辑**：
  - 预占：`available -= q`，`reserved += q`
  - 确认：只减 `reserved`（available 预占时已扣）
  - 释放：`available += q`，`reserved -= q`

---

## 五、第二版迭代记录（发现了哪些问题、如何定位、如何修正）

第一版是 2 小时限时版本，能跑通主流程但在「干净环境稳定运行 + 可验证」上有明显短板。第二版逐项修复，每个问题对应一次独立 commit，便于回溯。

| # | 问题 | 如何定位 | 如何修正 |
|---|------|----------|----------|
| 1 | `docker compose up --build` 在干净环境会因 app 抢在 Postgres 就绪前连库而退出 | 阅读 `main.py` 发现 `create_all()` 在**模块导入时**就执行；compose 仅用 `depends_on`（只保证启动顺序、不保证 DB ready） | ① db 加 `healthcheck`（`pg_isready`），app 改用 `depends_on: condition: service_healthy`；② app 启动增加 `wait_for_db()` 重试循环；③ 把建表/初始化从导入时挪到 lifespan 启动钩子 |
| 2 | 没有初始化 SKU001，接口无法直接测试 | 全代码没有任何 seed 逻辑，`create_all` 只建空表 | 在 lifespan 启动钩子里 `seed_initial_data()`，幂等插入 `SKU001 available=10, reserved=0`（已存在则跳过） |
| 3 | `quantity` 无合法性校验，负数会反向加库存 | `schemas.py` 中 `quantity: int` 无约束，负数能一路进入 `service.py` 执行 `available -= q` | `schemas.py` 改为 `Field(gt=0)`，非法值自动返回 422 |
| 4 | 重复 order_no 会触发数据库唯一约束抛 500，错误不清晰 | `service.py` 直接 `db.add` 后 commit，未预检查 | 预占前先查 order_no 是否存在，存在返回 **409**；并用 `IntegrityError` 兜底应对并发 |
| 5 | 没有任何测试 / 验证记录 | 仓库无测试文件 | 新增 `tests/test_api.py`（11 个用例）+ `verify.sh`（curl 冒烟脚本），覆盖反馈要求的全部场景 |
| 6 | 依赖未锁版本，不同机器可能装出不兼容版本 | `requirements.txt` 只有包名 | 锁定全部版本 |

### 验证用例覆盖

`tests/test_api.py` 覆盖反馈点名的全部场景：

1. 查询初始库存 → `available=10, reserved=0`
2. 成功预占 2 件 → 201 / RESERVED，库存变 8/2
3. 库存不足 → 400，库存不变
4. 释放订单 → 库存恢复 10/0
5. 确认订单 → available 不回补、reserved 清零
6. 非法状态：不能重复释放、确认后不能释放、不能重复确认 → 400
7. 负数/0 数量 → 422，库存不变
8. （额外）重复 order_no → 409，不重复扣库存

### 自验证过程中额外发现 / 想清楚的工程问题

除了对照反馈修复的 5 个问题，我在「亲自跑通 + 逐个接口验证」时还遇到并解决了：

1. **测试跑不进现有 app 容器**：`docker compose exec app pytest` 失败——`Dockerfile` 只 `COPY ./app`、生产镜像不含 pytest、`tests/` 也没打进镜像。为此新增 `Dockerfile.test` 和 compose `test` 服务，现在可 `docker compose run --rm test` 在容器里一键跑测试。
2. **「干净环境」需 `down -v` 才能复现**：数据存在 named volume `pgdata`，`docker compose down` 默认不删卷；叠加 seed 幂等（已存在则跳过），所以模拟全新环境必须 `down -v` 清卷再 `up`。
3. **seed 必须幂等**：直接 insert 会在重启时撞主键约束导致启动失败，因此改为「先查存在再插」，保证多次启动安全。
4. **负数返回 422 而非 400**：确认这是 Pydantic 参数校验的标准语义（参数本身非法=422，格式合法但业务规则不满足=400），不是 bug。
5. **消除 Pydantic v2 弃用警告**：跑测试时发现 `class Config` 弃用警告，改为 `ConfigDict`。
6. **环境网络坑**：GitHub 连接被重置、Docker Hub 拉 `python:3.11-slim` 超时，通过配置国内镜像加速器解决（正是第一版没解决的同一类网络问题，这次彻底跑通）。
7. **接口实测发现的两个行为**：SKU 区分大小写（`sku001` 查不到、`SKU001` 才行）；reserve 先校验 order_no 重复、再校验库存，所以用已存在的单号下单会先返回 409 而非 400。

---

## 六、AI 使用情况（真实分工）

**使用的工具**：ChatGPT / Cursor / Claude（代码生成与调试）、FastAPI / SQLAlchemy / PostgreSQL 官方文档。

**我怎么用 AI 的**：拿到面试反馈后，我把「反馈 + 第一版源码」一起交给 AI，要求严格对照反馈逐条修复，并先把每条问题定位到具体代码再改。AI 负责把我的修复意图落成代码和原理解释，我负责定方向、做验收、亲自跑通验证。

**AI 帮我做的**：
- 把 5 条反馈定位到具体代码行并给出实现：`healthcheck`、`wait_for_db()` 重试、lifespan 启动初始化、`Field(gt=0)` 校验、409 防重、pytest 用例。
- 解释每处改动背后的原理（lifespan 钩子、`depends_on` 与健康检查的区别、`with_for_update()` 悲观锁、Pydantic 校验等）。

**我自己判断 / 亲手做的**：
- 验收每一处改动是否真解决了对应反馈，理解后才接受。
- 在干净的 Windows + Docker 环境亲自运行 `docker compose up --build`，并解决了上面「自验证」一节里的网络坑、测试容器化、`down -v` 复现等问题。
- 想清楚几个设计取舍：seed 为什么要幂等、422 与 400 的语义边界、测试为什么用 SQLite（以及它和真 Postgres 行级锁的边界）。
- 决定保留简化状态机（合并 CREATED/RESERVED），并能说明理由与未来扩展点。

---

## 七、已知边界 / 后续可做

- 单元测试用 SQLite，**并发防超卖**需要在真 Postgres 上做并发压测验证，本版未覆盖。
- 未做鉴权、限流、分页等生产能力（题目范围之外）。
- 多 SKU、库存调拨等可在现有分层上平滑扩展。
