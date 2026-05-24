import React from 'react';
import { AppstoreOutlined } from '@ant-design/icons';
import { history, RequestConfig, RunTimeLayoutConfig } from '@umijs/max';
import { Divider, Space, Typography, message } from 'antd';

import HeaderUserMenu from '@/components/HeaderUserMenu';
import { clearSession, getSession } from '@/utils/session';

export const request: RequestConfig = {
  timeout: 10000,
  requestInterceptors: [
    (url, options) => {
      const session = getSession();
      if (!session?.access_token) {
        return { url, options };
      }

      return {
        url,
        options: {
          ...options,
          headers: {
            ...(options?.headers || {}),
            Authorization: `Bearer ${session.access_token}`,
          },
        },
      };
    },
  ],
  errorConfig: {
    errorHandler: (error: any, opts: any) => {
      if (opts?.skipErrorHandler) throw error;

      // 处理 401 未授权
      if (error?.response?.status === 401) {
        clearSession();
        message.warning('登录已失效，请重新登录');
        // 使用 window.location 强制跳转更稳定，且能彻底清理所有前端缓存状态
        window.location.href = '/login';
        return;
      }

      // 其他业务错误处理，提取后端返回的详细错误信息
      const errorInfo = error?.response?.data?.detail || error?.message || '请求出错，请稍后重试';
      message.error(String(errorInfo));
      throw error;
    },
  },
};

const PUBLIC_PATHS = ['/login'];

function hasSession() {
  return Boolean(getSession());
}

export const layout: RunTimeLayoutConfig = () => {
  return {
    layout: 'mix',
    headerTitleRender: () => {
      return React.createElement(
        Space,
        { size: 10 },
        React.createElement(AppstoreOutlined, { style: { fontSize: 18, color: '#1677ff' } }),
        React.createElement(Divider, { type: 'vertical', style: { margin: 0, height: 18 } }),
        React.createElement(
          Typography.Text,
          { strong: true, style: { fontSize: 14 } },
          '设备管理系统',
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
        history.push('/tenant');
      }
    },
  };
};
