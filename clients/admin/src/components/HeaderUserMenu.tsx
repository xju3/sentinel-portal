import { history } from '@umijs/max';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Dropdown, MenuProps, Space, message } from 'antd';
import { useRef } from 'react';

import { clearSession, getSession } from '@/utils/session';

const HeaderUserMenu = () => {
  const triggerRef = useRef<HTMLSpanElement>(null);
  const session = getSession();
  const displayName = session?.contact_name || session?.username || '未命名用户';

  const onMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'logout') {
      clearSession();
      message.success('已退出登录');
      history.push('/login');
    }
  };

  const items: MenuProps['items'] = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
    },
  ];

  return (
    <Dropdown menu={{ items, onClick: onMenuClick }} placement="bottomRight" trigger={['click']}>
      <span ref={triggerRef} style={{ display: 'inline-flex' }}>
        <Button type="text">
          <Space>
            <UserOutlined />
            {displayName}
          </Space>
        </Button>
      </span>
    </Dropdown>
  );
};

export default HeaderUserMenu;
