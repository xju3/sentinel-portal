import { history } from '@umijs/max';
import { LockOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Dropdown, MenuProps, Space, message } from 'antd';

import { clearSession, getSession } from '@/utils/session';

const HeaderUserMenu = () => {
  const session = getSession();
  const contactName = session?.contact_name || session?.username || '未命名用户';

  const onMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'profile') {
      history.push('/profile');
      return;
    }
    if (key === 'password') {
      history.push('/change-password');
      return;
    }
    if (key === 'logout') {
      clearSession();
      message.success('已退出登录');
      history.push('/login');
    }
  };

  const items: MenuProps['items'] = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人信息',
    },
    {
      key: 'password',
      icon: <LockOutlined />,
      label: '更改密码',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
    },
  ];

  return (
    <Dropdown menu={{ items, onClick: onMenuClick }} placement="bottomRight" trigger={['click']}>
      <Button type="text">
        <Space>
          <UserOutlined />
          {contactName}
        </Space>
      </Button>
    </Dropdown>
  );
};

export default HeaderUserMenu;
