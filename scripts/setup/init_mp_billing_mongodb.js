/**
 * 小程序 + 计费运营模块 MongoDB 初始化/迁移脚本
 *
 * 适用场景：在已有 tradingagents 库上增量部署新逻辑（会员、计费、充值）
 *
 * 用法（mongosh）：
 *   mongosh "mongodb://localhost:27017/tradingagents" scripts/setup/init_mp_billing_mongodb.js
 *
 * Docker 容器内：
 *   mongosh -u admin -p tradingagents123 --authenticationDatabase admin tradingagents /docker-entrypoint-initdb.d/init_mp_billing_mongodb.js
 *
 * 带认证：
 *   mongosh "mongodb://user:pass@host:27017/tradingagents?authSource=admin" scripts/setup/init_mp_billing_mongodb.js
 */

print('========================================');
print('小程序/计费模块 MongoDB 初始化开始');
print('========================================');

const dbName = 'tradingagents';
db = db.getSiblingDB(dbName);
const now = new Date();

// ===== 1. 创建集合 =====
print('\n[1/4] 创建集合...');

const newCollections = [
  'membership_levels',
  'billing_records',
  'payment_orders',
  'user_quota_usage',
];

newCollections.forEach(function (name) {
  const exists = db.getCollectionNames().indexOf(name) >= 0;
  if (!exists) {
    db.createCollection(name);
    print('  ✓ 创建集合: ' + name);
  } else {
    print('  · 集合已存在: ' + name);
  }
});

// ===== 2. 创建索引 =====
print('\n[2/4] 创建索引...');

// users 扩展索引（小程序 openid 唯一）
try {
  db.users.createIndex({ openid: 1 }, { unique: true, sparse: true, name: 'uniq_openid_sparse' });
  print('  ✓ users.uniq_openid_sparse');
} catch (e) {
  print('  · users.uniq_openid_sparse: ' + e.message);
}

try {
  db.users.createIndex({ user_type: 1, created_at: -1 }, { name: 'idx_user_type_created' });
  print('  ✓ users.idx_user_type_created');
} catch (e) {
  print('  · users.idx_user_type_created: ' + e.message);
}

try {
  db.users.createIndex({ membership_level_id: 1 }, { sparse: true, name: 'idx_membership_level_id' });
  print('  ✓ users.idx_membership_level_id');
} catch (e) {
  print('  · users.idx_membership_level_id: ' + e.message);
}

// membership_levels
try {
  db.membership_levels.createIndex({ code: 1 }, { unique: true, name: 'uniq_code' });
  db.membership_levels.createIndex({ is_default: 1, is_active: 1 }, { name: 'idx_default_active' });
  db.membership_levels.createIndex({ sort_order: 1 }, { name: 'idx_sort_order' });
  print('  ✓ membership_levels 索引');
} catch (e) {
  print('  · membership_levels: ' + e.message);
}

// billing_records
try {
  db.billing_records.createIndex({ user_id: 1, created_at: -1 }, { name: 'idx_user_created' });
  db.billing_records.createIndex({ action_type: 1, created_at: -1 }, { name: 'idx_action_created' });
  db.billing_records.createIndex({ order_no: 1 }, { sparse: true, name: 'idx_order_no' });
  db.billing_records.createIndex({ task_id: 1 }, { sparse: true, name: 'idx_task_id' });
  db.billing_records.createIndex({ stock_code: 1, created_at: -1 }, { sparse: true, name: 'idx_stock_created' });
  print('  ✓ billing_records 索引');
} catch (e) {
  print('  · billing_records: ' + e.message);
}

// payment_orders
try {
  db.payment_orders.createIndex({ order_no: 1 }, { unique: true, name: 'uniq_order_no' });
  db.payment_orders.createIndex({ user_id: 1, created_at: -1 }, { name: 'idx_user_created' });
  db.payment_orders.createIndex({ status: 1, created_at: -1 }, { name: 'idx_status_created' });
  db.payment_orders.createIndex({ wx_transaction_id: 1 }, { sparse: true, name: 'idx_wx_transaction_id' });
  print('  ✓ payment_orders 索引');
} catch (e) {
  print('  · payment_orders: ' + e.message);
}

// user_quota_usage（每月免费额度）
try {
  db.user_quota_usage.createIndex({ user_id: 1, period: 1 }, { unique: true, name: 'uniq_user_period' });
  db.user_quota_usage.createIndex({ period: 1 }, { name: 'idx_period' });
  print('  ✓ user_quota_usage 索引');
} catch (e) {
  print('  · user_quota_usage: ' + e.message);
}

// analysis_tasks 小程序查询优化
try {
  db.analysis_tasks.createIndex({ user_id: 1, status: 1, created_at: -1 }, { name: 'idx_user_status_created' });
  print('  ✓ analysis_tasks.idx_user_status_created');
} catch (e) {
  print('  · analysis_tasks: ' + e.message);
}

// ===== 3. 初始化会员等级 =====
print('\n[3/4] 初始化会员等级...');

const levelCount = db.membership_levels.countDocuments({});
if (levelCount === 0) {
  const defaultLevels = [
    {
      name: '普通用户',
      code: 'normal',
      sort_order: 0,
      monthly_free_generations: 0,
      per_generation_price: 9.9,
      monthly_price: null,
      description: '按次付费，无免费额度',
      is_default: true,
      is_active: true,
      created_at: now,
      updated_at: now,
    },
    {
      name: '银卡会员',
      code: 'silver',
      sort_order: 1,
      monthly_free_generations: 3,
      per_generation_price: 6.9,
      monthly_price: null,
      description: '每月 3 次免费生成，超出按 6.9 元/次',
      is_default: false,
      is_active: true,
      created_at: now,
      updated_at: now,
    },
    {
      name: '金卡会员',
      code: 'gold',
      sort_order: 2,
      monthly_free_generations: 10,
      per_generation_price: 4.9,
      monthly_price: null,
      description: '每月 10 次免费生成，超出按 4.9 元/次',
      is_default: false,
      is_active: true,
      created_at: now,
      updated_at: now,
    },
  ];
  db.membership_levels.insertMany(defaultLevels);
  print('  ✓ 已插入 ' + defaultLevels.length + ' 个默认会员等级');
} else {
  print('  · 会员等级已存在，跳过插入（共 ' + levelCount + ' 条）');
}

const defaultLevel = db.membership_levels.findOne({ is_default: true, is_active: true })
  || db.membership_levels.findOne({ is_active: true }, { sort: { sort_order: 1 } });
const defaultLevelId = defaultLevel ? String(defaultLevel._id) : null;

// ===== 4. 迁移已有 users 文档 =====
print('\n[4/4] 迁移 users 集合扩展字段...');

const userMigration = {
  user_type: 'admin',
  openid: null,
  unionid: null,
  nickname: null,
  avatar_url: null,
  phone: null,
  membership_level_id: defaultLevelId,
  balance: 0.0,
};

const migrateResult = db.users.updateMany(
  {
    $or: [
      { user_type: { $exists: false } },
      { balance: { $exists: false } },
    ],
  },
  { $set: userMigration }
);

print('  ✓ users 迁移 matched=' + migrateResult.matchedCount + ', modified=' + migrateResult.modifiedCount);

// 确保已有 admin 用户 user_type 为 admin（避免误标为 mp_user）
db.users.updateMany(
  { is_admin: true, user_type: { $ne: 'mp_user' } },
  { $set: { user_type: 'admin', updated_at: now } }
);

// ===== 验证 =====
print('\n========================================');
print('验证结果');
print('========================================');
print('membership_levels: ' + db.membership_levels.countDocuments({}));
print('billing_records:   ' + db.billing_records.countDocuments({}));
print('payment_orders:    ' + db.payment_orders.countDocuments({}));
print('user_quota_usage:  ' + db.user_quota_usage.countDocuments({}));
print('users (mp_user):   ' + db.users.countDocuments({ user_type: 'mp_user' }));
print('users (admin):     ' + db.users.countDocuments({ user_type: 'admin' }));
if (defaultLevel) {
  print('默认会员等级:      ' + defaultLevel.name + ' (' + defaultLevel.code + ')');
}
print('========================================');
print('小程序/计费模块 MongoDB 初始化完成');
print('========================================');
