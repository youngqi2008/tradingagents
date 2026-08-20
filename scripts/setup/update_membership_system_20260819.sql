-- 会员体系升级脚本（来源：data/会员等级与费用明细.xlsx）
-- 用法: mysql -u root -p ares_ops < scripts/setup/update_membership_system_20260819.sql
--
-- 说明：
-- 1. 免费额度通过 benefit_campaigns 发放（grant_mode=default），等级表仅配置月费与超限单价
-- 2. push_quota 对应 Excel「AI深度分析」
-- 3. 月度权益配额以 Excel「说明」列为准；表头「/年」列用于单价校验
-- 4. 执行后重启 backend 会幂等同步代码侧默认配置

USE ares_ops;

START TRANSACTION;

-- ---------------------------------------------------------------------------
-- 1. 旧等级迁移：vip -> platinum
-- ---------------------------------------------------------------------------
UPDATE users u
INNER JOIN membership_levels old_lv ON u.membership_level_id = old_lv.id AND old_lv.code = 'vip'
INNER JOIN membership_levels new_lv ON new_lv.code = 'platinum'
SET u.membership_level_id = new_lv.id;

-- ---------------------------------------------------------------------------
-- 2. 会员等级（7 档）
-- ---------------------------------------------------------------------------
UPDATE membership_levels SET is_default = 0;

INSERT INTO membership_levels (
  name, code, sort_order,
  monthly_free_generations, per_generation_price,
  monthly_free_asks, per_ask_price,
  monthly_price, description, is_default, is_active
) VALUES
  ('体验会员', 'trial', 0, 0, 100.00, 0, 20.00, 199.00,
   '了解基础功能；基础问股，含每月免费额度', 0, 1),
  ('普通会员', 'normal', 1, 0, 90.00, 0, 18.00, 888.00,
   '按次付费，无免费额度；无广告', 1, 1),
  ('银卡会员', 'silver', 2, 0, 75.00, 0, 15.00, 1888.00,
   '每月3次免费研报；优先客服，每月20次研报权益', 0, 1),
  ('金卡会员', 'gold', 3, 0, 65.00, 0, 13.00, 2888.00,
   '每月10次免费研报；专属客服，每月40次研报权益', 0, 1),
  ('白金会员', 'platinum', 4, 0, 55.00, 0, 11.00, 3888.00,
   '入门权益+每月研报5次/问股20次/AI深度分析8次；策略组合推荐', 0, 1),
  ('钻石会员', 'diamond', 5, 0, 25.00, 0, 8.00, 5888.00,
   '深度分析优先；每月50次AI深度分析；专属研究报告', 0, 1),
  ('至尊会员', 'supreme', 6, 0, 15.00, 0, 5.00, 38888.00,
   '最优权益；每月1000次问股/150次AI深度分析；1V1专属顾问', 0, 1)
ON DUPLICATE KEY UPDATE
  name = VALUES(name),
  sort_order = VALUES(sort_order),
  monthly_free_generations = 0,
  per_generation_price = VALUES(per_generation_price),
  monthly_free_asks = 0,
  per_ask_price = VALUES(per_ask_price),
  monthly_price = VALUES(monthly_price),
  description = VALUES(description),
  is_default = VALUES(is_default),
  is_active = 1,
  updated_at = CURRENT_TIMESTAMP(6);

-- 停用旧 vip 等级
UPDATE membership_levels SET is_active = 0, is_default = 0 WHERE code = 'vip';

-- ---------------------------------------------------------------------------
-- 3. 下线旧默认权益活动
-- ---------------------------------------------------------------------------
UPDATE benefit_campaigns
SET status = 'ended', updated_at = CURRENT_TIMESTAMP(6)
WHERE code IN (
  'level_normal_welcome',
  'level_vip_welcome',
  'level_vip_monthly'
);

-- ---------------------------------------------------------------------------
-- 4. 新默认权益活动（按等级 code 关联）
-- ---------------------------------------------------------------------------

-- 体验会员 · 每月
INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '体验会员·每月权益', 'level_trial_monthly',
  '体验会员每月刷新：研报3次、问股5次、AI深度分析2次',
  'active', 'membership', 'default', ml.id, 'monthly', 3, 5, 2, 1, 100
FROM membership_levels ml WHERE ml.code = 'trial'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'trial' LIMIT 1),
  cycle_type = 'monthly', report_quota = 3, ask_quota = 5, push_quota = 2,
  stackable = 1, priority = 100, updated_at = CURRENT_TIMESTAMP(6);

-- 银卡 · 入门 + 每月
INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '银卡会员·入门权益', 'level_silver_welcome',
  '银卡一次性权益：研报10次、问股20次、AI深度分析5次',
  'active', 'membership', 'default', ml.id, 'once', 10, 20, 5, 1, 90
FROM membership_levels ml WHERE ml.code = 'silver'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'silver' LIMIT 1),
  cycle_type = 'once', report_quota = 10, ask_quota = 20, push_quota = 5,
  stackable = 1, priority = 90, updated_at = CURRENT_TIMESTAMP(6);

INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '银卡会员·每月权益', 'level_silver_monthly',
  '银卡每月刷新：研报3次、问股20次、AI深度分析10次',
  'active', 'membership', 'default', ml.id, 'monthly', 3, 20, 10, 1, 80
FROM membership_levels ml WHERE ml.code = 'silver'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'silver' LIMIT 1),
  cycle_type = 'monthly', report_quota = 3, ask_quota = 20, push_quota = 10,
  stackable = 1, priority = 80, updated_at = CURRENT_TIMESTAMP(6);

-- 金卡 · 入门 + 每月
INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '金卡会员·入门权益', 'level_gold_welcome',
  '金卡一次性权益：研报15次、问股30次、AI深度分析10次',
  'active', 'membership', 'default', ml.id, 'once', 15, 30, 10, 1, 70
FROM membership_levels ml WHERE ml.code = 'gold'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'gold' LIMIT 1),
  cycle_type = 'once', report_quota = 15, ask_quota = 30, push_quota = 10,
  stackable = 1, priority = 70, updated_at = CURRENT_TIMESTAMP(6);

INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '金卡会员·每月权益', 'level_gold_monthly',
  '金卡每月刷新：研报10次、问股30次、AI深度分析20次',
  'active', 'membership', 'default', ml.id, 'monthly', 10, 30, 20, 1, 60
FROM membership_levels ml WHERE ml.code = 'gold'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'gold' LIMIT 1),
  cycle_type = 'monthly', report_quota = 10, ask_quota = 30, push_quota = 20,
  stackable = 1, priority = 60, updated_at = CURRENT_TIMESTAMP(6);

-- 白金 · 入门 + 每月
INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '白金会员·入门权益', 'level_platinum_welcome',
  '白金一次性权益：研报15次、问股30次、AI深度分析10次',
  'active', 'membership', 'default', ml.id, 'once', 15, 30, 10, 1, 55
FROM membership_levels ml WHERE ml.code = 'platinum'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'platinum' LIMIT 1),
  cycle_type = 'once', report_quota = 15, ask_quota = 30, push_quota = 10,
  stackable = 1, priority = 55, updated_at = CURRENT_TIMESTAMP(6);

INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '白金会员·每月权益', 'level_platinum_monthly',
  '白金每月刷新：研报5次、问股20次、AI深度分析8次',
  'active', 'membership', 'default', ml.id, 'monthly', 5, 20, 8, 1, 50
FROM membership_levels ml WHERE ml.code = 'platinum'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'platinum' LIMIT 1),
  cycle_type = 'monthly', report_quota = 5, ask_quota = 20, push_quota = 8,
  stackable = 1, priority = 50, updated_at = CURRENT_TIMESTAMP(6);

-- 钻石 · 入门 + 每月
INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '钻石会员·入门权益', 'level_diamond_welcome',
  '钻石一次性权益：研报30次、问股60次、AI深度分析20次',
  'active', 'membership', 'default', ml.id, 'once', 30, 60, 20, 1, 45
FROM membership_levels ml WHERE ml.code = 'diamond'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'diamond' LIMIT 1),
  cycle_type = 'once', report_quota = 30, ask_quota = 60, push_quota = 20,
  stackable = 1, priority = 45, updated_at = CURRENT_TIMESTAMP(6);

INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '钻石会员·每月权益', 'level_diamond_monthly',
  '钻石每月刷新：研报30次、问股60次、AI深度分析50次',
  'active', 'membership', 'default', ml.id, 'monthly', 30, 60, 50, 1, 40
FROM membership_levels ml WHERE ml.code = 'diamond'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'diamond' LIMIT 1),
  cycle_type = 'monthly', report_quota = 30, ask_quota = 60, push_quota = 50,
  stackable = 1, priority = 40, updated_at = CURRENT_TIMESTAMP(6);

-- 至尊 · 入门 + 每月
INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '至尊会员·入门权益', 'level_supreme_welcome',
  '至尊一次性权益：研报100次、问股200次、AI深度分析50次',
  'active', 'membership', 'default', ml.id, 'once', 100, 200, 50, 1, 35
FROM membership_levels ml WHERE ml.code = 'supreme'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'supreme' LIMIT 1),
  cycle_type = 'once', report_quota = 100, ask_quota = 200, push_quota = 50,
  stackable = 1, priority = 35, updated_at = CURRENT_TIMESTAMP(6);

INSERT INTO benefit_campaigns (
  name, code, description, status, grant_scope, grant_mode,
  membership_level_id, cycle_type, report_quota, ask_quota, push_quota,
  stackable, priority
)
SELECT
  '至尊会员·每月权益', 'level_supreme_monthly',
  '至尊每月刷新：研报不限、问股1000次、AI深度分析150次',
  'active', 'membership', 'default', ml.id, 'monthly', 99999, 1000, 150, 1, 30
FROM membership_levels ml WHERE ml.code = 'supreme'
ON DUPLICATE KEY UPDATE
  name = VALUES(name), description = VALUES(description), status = 'active',
  grant_scope = 'membership', grant_mode = 'default',
  membership_level_id = (SELECT id FROM membership_levels WHERE code = 'supreme' LIMIT 1),
  cycle_type = 'monthly', report_quota = 99999, ask_quota = 1000, push_quota = 150,
  stackable = 1, priority = 30, updated_at = CURRENT_TIMESTAMP(6);

COMMIT;

-- 验证
SELECT code, name, sort_order, monthly_price, per_generation_price, per_ask_price, is_default, is_active
FROM membership_levels ORDER BY sort_order;

SELECT bc.code, bc.name, bc.cycle_type, bc.report_quota, bc.ask_quota, bc.push_quota, bc.status, ml.code AS level_code
FROM benefit_campaigns bc
LEFT JOIN membership_levels ml ON ml.id = bc.membership_level_id
WHERE bc.grant_mode = 'default' AND bc.code LIKE 'level_%'
ORDER BY ml.sort_order, bc.priority DESC;
