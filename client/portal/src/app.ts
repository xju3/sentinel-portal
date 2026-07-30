import React from 'react';
import { AppstoreOutlined } from '@ant-design/icons';
import { history, RequestConfig, RunTimeLayoutConfig } from '@umijs/max';
import { Divider, Space, Typography, message } from 'antd';

import HeaderUserMenu from '@/components/HeaderUserMenu';
import { clearSession, getSession } from '@/utils/session';

const WX_DIAGNOSIS_ROUTE_PREFIX = '/wx/diagnosis/';
const WX_DIAGNOSIS_API_PREFIX = '/api/v1/wx/diagnosis/';

function isWxDiagnosisPath(pathname?: string | null) {
  return Boolean(pathname && pathname.startsWith(WX_DIAGNOSIS_ROUTE_PREFIX));
}

function isWxDiagnosisApi(url?: string | null) {
  return Boolean(url && url.includes(WX_DIAGNOSIS_API_PREFIX));
}

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
        const requestUrl = response.config?.url;
        const wxDiagnosisRequest = isWxDiagnosisApi(requestUrl);

        // Check for unauthorized (code === 401)
        if (body && body.code === 401) {
          const errorMessage = body.message || 'Unauthorized';
          if (wxDiagnosisRequest) {
            return Promise.reject(Object.assign(new Error(errorMessage), {
              code: body.code,
              data: { detail: errorMessage },
            }));
          }
          clearSession();
          const isLoginRequest = requestUrl?.includes('/auth/login');
          if (!isLoginRequest && window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
          return Promise.reject(Object.assign(new Error(errorMessage), {
            code: body.code,
            data: { detail: errorMessage },
          }));
        }

        if (body && body.code === 403 && wxDiagnosisRequest) {
          const errorMessage = body.message || 'Forbidden';
          return Promise.reject(Object.assign(new Error(errorMessage), {
            code: body.code,
            data: { detail: errorMessage },
          }));
        }

        // Reject business errors even though the API transports them with HTTP 200.
        if (body && body.code !== 0 && body.code !== 200 && body.code !== 202 && body.code !== undefined) {
          const errorMessage = body.message || `Error (code: ${body.code})`;
          if (!wxDiagnosisRequest) {
            message.error(errorMessage);
          }
          const businessError = Object.assign(new Error(errorMessage), {
            code: body.code,
            data: { detail: errorMessage },
            businessErrorShown: !wxDiagnosisRequest,
          });
          return Promise.reject(businessError);
        }

        // Add success field so umi doesn't pop up default errors
        if (body && (body.code === 0 || body.code === 200 || body.code === 202)) {
          body.success = true;
        }

        // Unwrap the ApiResponse: replace response.data with body.data
        // so that request<T>() returns the data field directly
        if (body && body.code === 0 && body.data !== undefined) {
          response.data = body.data;
        }
      } catch (e) {
        // If parsing fails, fall back to HTTP status check
        if (response.status === 401 || response.status === 403) {
          const wxDiagnosisRequest = isWxDiagnosisApi(response.config?.url);
          if (wxDiagnosisRequest) {
            const detail = response.status === 403 ? 'Forbidden' : 'Unauthorized';
            return Promise.reject(Object.assign(new Error(detail), {
              code: response.status,
              data: { detail },
            }));
          }
        }
        if (response.status === 401) {
          clearSession();
          const isLoginRequest = response.config?.url?.includes('/auth/login');
          if (!isLoginRequest && window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
          return Promise.reject(Object.assign(new Error('Unauthorized'), {
            code: 401,
            data: { detail: 'Unauthorized' },
          }));
        }
        if (response.status === 403) {
          return Promise.reject(Object.assign(new Error('Forbidden'), {
            code: 403,
            data: { detail: 'Forbidden' },
          }));
        }
      }
      return response;
    },
  ],
};

const PUBLIC_PATHS = ['/login', '/register', '/set-password'];
const GUEST_ONLY_PATHS = ['/login', '/register'];

function isPublicPath(pathname: string) {
  return PUBLIC_PATHS.includes(pathname) || isWxDiagnosisPath(pathname);
}

function hasSession() {
  return Boolean(getSession());
}

export const layout: RunTimeLayoutConfig = () => {
  return {
    layout: 'mix',
    headerTitleRender: () => {
      const session = getSession();
      const tenantName = session?.tenant_name || '未识别租户';
      return React.createElement(
        Space,
        { size: 10 },
        React.createElement(AppstoreOutlined, { style: { fontSize: 18, color: '#1677ff' } }),
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
      if (!loggedIn && !isPublicPath(pathname)) {
        history.push('/login');
        return;
      }
      if (loggedIn && GUEST_ONLY_PATHS.includes(pathname)) {
        history.push('/dashboard/overview');
      }
    },
  };
};
