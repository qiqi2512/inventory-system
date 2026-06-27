#!/usr/bin/env bash
#
# 针对「真实运行的服务」做端到端冒烟验证（对应 README 里的手动验证步骤）。
# 用法：先 `docker compose up --build` 起服务，再另开终端执行 `bash verify.sh`
#
set -euo pipefail
BASE="${BASE:-http://localhost:8000}"

# 小工具：打印步骤标题
step() { echo; echo "==== $1 ===="; }

step "1. 查询初始库存（期望 available=10, reserved=0）"
curl -s "$BASE/inventory/SKU001"; echo

step "2. 成功预占 2 件（期望 201, status=RESERVED）"
curl -s -X POST "$BASE/reserve" -H 'Content-Type: application/json' \
  -d '{"order_no":"ORD-1","sku":"SKU001","quantity":2}'; echo
curl -s "$BASE/inventory/SKU001"; echo "  <- 期望 available=8, reserved=2"

step "3. 库存不足（quantity=100，期望 400 Insufficient inventory）"
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE/reserve" \
  -H 'Content-Type: application/json' \
  -d '{"order_no":"ORD-2","sku":"SKU001","quantity":100}'

step "4. 负数数量（期望 422，被参数校验拦截）"
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE/reserve" \
  -H 'Content-Type: application/json' \
  -d '{"order_no":"ORD-3","sku":"SKU001","quantity":-5}'

step "5. 重复 order_no（期望 409）"
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE/reserve" \
  -H 'Content-Type: application/json' \
  -d '{"order_no":"ORD-1","sku":"SKU001","quantity":1}'

step "6. 确认订单 ORD-1（期望 200, status=CONFIRMED）"
curl -s -X POST "$BASE/confirm" -H 'Content-Type: application/json' \
  -d '{"order_no":"ORD-1"}'; echo
curl -s "$BASE/inventory/SKU001"; echo "  <- 期望 available=8, reserved=0"

step "7. 非法状态：确认后再释放（期望 400）"
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE/release" \
  -H 'Content-Type: application/json' \
  -d '{"order_no":"ORD-1"}'

echo; echo "==== 冒烟验证结束 ===="
