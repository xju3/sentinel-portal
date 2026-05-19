import { Typography } from 'antd';

import { getSession } from '@/utils/session';

const HeaderLeftTenant = () => {
  const session = getSession();
  const tenantName = session?.tenant_name || '未识别租户';

  return (
    <Typography.Text strong style={{ fontSize: 14 }}>
      {tenantName}
    </Typography.Text>
  );
};

export default HeaderLeftTenant;
