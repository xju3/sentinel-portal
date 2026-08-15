-- Migration: add wx_union_id to account table
-- Date: 20260814
-- Description: Add wx_union_id field for WeChat Open Platform cross-app user binding.

ALTER TABLE account
    ADD COLUMN wx_union_id VARCHAR(255) DEFAULT NULL
    COMMENT 'WeChat Open Platform UnionID';

-- Ensure uniqueness (one account per union id)
ALTER TABLE account
    ADD UNIQUE INDEX uq_account_wx_union_id (wx_union_id);

ALTER TABLE employee
    ADD COLUMN wx_union_id VARCHAR(255) DEFAULT NULL
    COMMENT 'WeChat Open Platform UnionID';

ALTER TABLE employee
    ADD UNIQUE INDEX uq_employee_wx_union_id (wx_union_id);
