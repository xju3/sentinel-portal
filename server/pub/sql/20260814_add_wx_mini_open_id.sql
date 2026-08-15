-- Migration: add wx_mini_open_id to account table
-- Date: 20260814
-- Description: Add wx_mini_open_id field for WeChat Mini Program user binding.
--              This field is separate from wx_user_id (Official Account openid)
--              because Mini Program openids are scoped to the mini app's appid.

ALTER TABLE account
    ADD COLUMN wx_mini_open_id VARCHAR(255) DEFAULT NULL
    COMMENT 'WeChat Mini Program openid (scoped to mini app appid)';

-- Ensure uniqueness (one account per mini app user)
ALTER TABLE account
    ADD UNIQUE INDEX uq_account_wx_mini_open_id (wx_mini_open_id);
