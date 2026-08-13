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
  responseInterceptors: [
    async (response) => {
      // Parse the unified ApiResponse body from axios response.data
      try {
        const body = response.data;
        // Check for unauthorized (code === 401)
        if (body && body.code === 401) {
          clearSession();
          message.warning('登录已失效，请重新登录');
          // Force page reload to login page, preventing any further data processing
          window.location.href = '/login';
          // Return a rejected promise so the caller's .catch() is triggered
          return Promise.reject(new Error(body.message || 'Unauthorized'));
        }

        // For other error codes, show error message and reject promise
        if (body && body.code !== 0 && body.code !== 200 && body.code !== 202 && body.code !== undefined) {
          const errMsg = body.message || `Error (code: ${body.code})`;
          message.error(errMsg);
          return Promise.reject(new Error(errMsg));
        }

        // Unwrap the ApiResponse: replace response.data with body.data
        // so that request<T>() returns the data field directly
        if (body && (body.code === 0 || body.code === 200)) {
          response.data = body.data !== undefined ? body.data : body;
          response.data.success = true;
        } else if (body && body.code === 202) {
          response.data = body;
          response.data.success = true;
        }
      } catch (e) {
        // If parsing fails, fall back to HTTP status check
        if (response.status === 401) {
          clearSession();
          message.warning('登录已失效，请重新登录');
          window.location.href = '/login';
          return Promise.reject(new Error('Unauthorized'));
        }
      }
      return response;
    },
  ],
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
        history.push('/account/tenant');
      }
    },
  };
};
