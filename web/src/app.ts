import React from 'react';
import { history, RequestConfig, RunTimeLayoutConfig } from '@umijs/max';
import { Divider, Space, Typography } from 'antd';

import HeaderUserMenu from '@/components/HeaderUserMenu';
import { getSession } from '@/utils/session';

export const request: RequestConfig = {
  timeout: 10000,
};

const PUBLIC_PATHS = ['/login', '/register'];

function hasSession() {
  return Boolean(getSession());
}

export const layout: RunTimeLayoutConfig = () => {
  return {
    menuHeaderRender: false,
    headerTitleRender: () => {
      const session = getSession();
      const tenantName = session?.tenant_name || '未识别租户';
      return React.createElement(
        Space,
        { size: 10 },
        React.createElement(
          Typography.Text,
          { strong: true, style: { fontSize: 16 } },
          'Portal',
        ),
        React.createElement(Divider, { type: 'vertical', style: { margin: 0, height: 18 } }),
        React.createElement(
          Typography.Text,
          { strong: true, style: { fontSize: 14 } },
          tenantName,
        ),
      );
    },
    rightContentRender: () => React.createElement(HeaderUserMenu),
    onPageChange: () => {
      const pathname = history.location?.pathname || '/';
      const loggedIn = hasSession();
      if (!loggedIn && !PUBLIC_PATHS.includes(pathname)) {
        history.push('/login');
        return;
      }
      if (loggedIn && PUBLIC_PATHS.includes(pathname)) {
        history.push('/device/categories');
      }
    },
  };
};
