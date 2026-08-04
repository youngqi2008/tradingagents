#!/usr/bin/env python3
"""
小程序 + 计费运营模块 MongoDB 初始化/迁移脚本（Python 版）

功能：
  1. 创建 membership_levels / billing_records / payment_orders / user_quota_usage 集合
  2. 创建索引
  3. 插入默认会员等级（仅当表为空）
  4. 为已有 users 文档补全计费相关字段

用法：
  cd TradingAgents-CN
  python scripts/setup/init_mp_billing_mongodb.py

环境变量（与 .env 一致）：
  MONGODB_HOST / MONGODB_PORT / MONGODB_DATABASE
  MONGODB_USERNAME / MONGODB_PASSWORD / MONGODB_AUTH_SOURCE
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, MongoClient


def build_mongo_uri() -> str:
    host = os.getenv("MONGODB_HOST", "localhost")
    port = int(os.getenv("MONGODB_PORT", "27017"))
    db = os.getenv("MONGODB_DATABASE", "tradingagents")
    user = os.getenv("MONGODB_USERNAME", "")
    pwd = os.getenv("MONGODB_PASSWORD", "")
    auth_src = os.getenv("MONGODB_AUTH_SOURCE", "admin")
    if user and pwd:
        return f"mongodb://{user}:{pwd}@{host}:{port}/{db}?authSource={auth_src}"
    return f"mongodb://{host}:{port}/{db}"


DEFAULT_LEVELS = [
    {
        "name": "普通用户",
        "code": "normal",
        "sort_order": 0,
        "monthly_free_generations": 0,
        "per_generation_price": 9.9,
        "monthly_price": None,
        "description": "按次付费，无免费额度",
        "is_default": True,
        "is_active": True,
    },
    {
        "name": "银卡会员",
        "code": "silver",
        "sort_order": 1,
        "monthly_free_generations": 3,
        "per_generation_price": 6.9,
        "monthly_price": None,
        "description": "每月 3 次免费生成，超出按 6.9 元/次",
        "is_default": False,
        "is_active": True,
    },
    {
        "name": "金卡会员",
        "code": "gold",
        "sort_order": 2,
        "monthly_free_generations": 10,
        "per_generation_price": 4.9,
        "monthly_price": None,
        "description": "每月 10 次免费生成，超出按 4.9 元/次",
        "is_default": False,
        "is_active": True,
    },
]


def ensure_indexes(db) -> None:
    users = db["users"]
    users.create_index([("openid", ASCENDING)], unique=True, sparse=True, name="uniq_openid_sparse")
    users.create_index([("user_type", ASCENDING), ("created_at", DESCENDING)], name="idx_user_type_created")
    users.create_index([("membership_level_id", ASCENDING)], sparse=True, name="idx_membership_level_id")

    levels = db["membership_levels"]
    levels.create_index([("code", ASCENDING)], unique=True, name="uniq_code")
    levels.create_index([("is_default", ASCENDING), ("is_active", ASCENDING)], name="idx_default_active")
    levels.create_index([("sort_order", ASCENDING)], name="idx_sort_order")

    billing = db["billing_records"]
    billing.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_user_created")
    billing.create_index([("action_type", ASCENDING), ("created_at", DESCENDING)], name="idx_action_created")
    billing.create_index([("order_no", ASCENDING)], sparse=True, name="idx_order_no")
    billing.create_index([("task_id", ASCENDING)], sparse=True, name="idx_task_id")
    billing.create_index([("stock_code", ASCENDING), ("created_at", DESCENDING)], sparse=True, name="idx_stock_created")

    orders = db["payment_orders"]
    orders.create_index([("order_no", ASCENDING)], unique=True, name="uniq_order_no")
    orders.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_user_created")
    orders.create_index([("status", ASCENDING), ("created_at", DESCENDING)], name="idx_status_created")
    orders.create_index([("wx_transaction_id", ASCENDING)], sparse=True, name="idx_wx_transaction_id")

    quota = db["user_quota_usage"]
    quota.create_index([("user_id", ASCENDING), ("period", ASCENDING)], unique=True, name="uniq_user_period")
    quota.create_index([("period", ASCENDING)], name="idx_period")

    tasks = db["analysis_tasks"]
    tasks.create_index(
        [("user_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
        name="idx_user_status_created",
    )
    print("✅ 索引创建完成")


def init_membership_levels(db) -> str | None:
    coll = db["membership_levels"]
    now = datetime.now(timezone.utc)
    if coll.count_documents({}) == 0:
        docs = [{**lv, "created_at": now, "updated_at": now} for lv in DEFAULT_LEVELS]
        coll.insert_many(docs)
        print(f"✅ 已插入 {len(docs)} 个默认会员等级")
    else:
        print(f"· 会员等级已存在，跳过插入（共 {coll.count_documents({})} 条）")

    default = coll.find_one({"is_default": True, "is_active": True}) or coll.find_one(
        {"is_active": True}, sort=[("sort_order", ASCENDING)]
    )
    return str(default["_id"]) if default else None


def migrate_users(db, default_level_id: str | None) -> None:
    now = datetime.now(timezone.utc)
    migration = {
        "user_type": "admin",
        "openid": None,
        "unionid": None,
        "nickname": None,
        "avatar_url": None,
        "phone": None,
        "membership_level_id": default_level_id,
        "balance": 0.0,
    }
    result = db["users"].update_many(
        {"$or": [{"user_type": {"$exists": False}}, {"balance": {"$exists": False}}]},
        {"$set": migration},
    )
    print(f"✅ users 迁移 matched={result.matched_count}, modified={result.modified_count}")

    db["users"].update_many(
        {"is_admin": True, "user_type": {"$ne": "mp_user"}},
        {"$set": {"user_type": "admin", "updated_at": now}},
    )


def main() -> int:
    uri = build_mongo_uri()
    db_name = os.getenv("MONGODB_DATABASE", "tradingagents")
    print(f"连接 MongoDB: {db_name}")

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[db_name]

    for name in ("membership_levels", "billing_records", "payment_orders", "user_quota_usage"):
        if name not in db.list_collection_names():
            db.create_collection(name)
            print(f"✅ 创建集合: {name}")

    ensure_indexes(db)
    default_level_id = init_membership_levels(db)
    migrate_users(db, default_level_id)

    print("\n--- 验证 ---")
    print(f"membership_levels: {db.membership_levels.count_documents({})}")
    print(f"billing_records:   {db.billing_records.count_documents({})}")
    print(f"payment_orders:    {db.payment_orders.count_documents({})}")
    print(f"users (mp_user):   {db.users.count_documents({'user_type': 'mp_user'})}")
    print(f"users (admin):     {db.users.count_documents({'user_type': 'admin'})}")
    print("✅ 小程序/计费模块 MongoDB 初始化完成")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"❌ 初始化失败: {e}", file=sys.stderr)
        raise SystemExit(1)
