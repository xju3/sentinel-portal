import { defineConfig } from '@umijs/max';
import { Children } from 'react';

export default defineConfig({
  npmClient: 'npm',
  antd: {},
  proxy: {
    '/api': {
      target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
      changeOrigin: true,
    },
    '/MP_verify_ltw6GHMtM4LrSug3.txt': {
      target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
      changeOrigin: true,
    },
  },
  layout: {
    title: 'Admin',
    logo: 'https://preview.pro.ant.design/static/logo.f0355d39.svg',
    layout: 'mix',
    splitMenus: false,
    navTheme: 'dark',
    headerTheme: 'light',
    fixedHeader: true,
    fixSiderbar: true,
    contentWidth: 'Fluid',
  },
  model: {},
  request: {},
  routes: [
    {
      path: '/login',
      component: '@/pages/Login',
      layout: false,
    },
    {
      path: '/account',
      name: '账号管理',
      icon: 'UserOutlined',
      routes: [
        {
          path: '/account/tenant',
          name: '租户管理',
          component: '@/pages/Tenant',
        },
        {
          path: '/account/user',
          name: '系统用户',
          component: '@/pages/Account',
        },
        {
          path: '/account',
          redirect: '/account/tenant',
        },
      ],
    },
    {
      path: '/production',
      name: '生产管理',
      icon: 'RadarChartOutlined',
      routes: [
        {
          path: '/production/type',
          name: '型号规格',
          component: '@/pages/Sensor/Type',
        },
        {
          path: '/production/batch',
          name: '生产批次',
          component: '@/pages/Sensor/Batch',
        },
        {
          path: '/production/product',
          name: '产品列表',
          component: '@/pages/Sensor/Product',
        },

        {
          path: '/production',
          redirect: '/production/type',
        },
      ],
    },
     {
      path: "/maintainance",
      name: "维护管理",
      icon: "ToolOutlined",
      routes: [
        {
          path: '/maintainance/firmware',
          name: '固件升级',
          component: '@/pages/Sensor/Firmware',
        },
        {
          path: '/maintainance/sim-card',
          name: 'SIM卡管理',
          component: '@/pages/SImCard',
        },
        {
          path: '/maintainance/task',
          name: '任务管理',
          component: '@/pages/Sensor/Task',
        },
        {
          path: '/maintainance',
          redirect: '/maintainance/firmware',
        },
      ]
    },
    {
      path: '/',
      redirect: '/login',
    },
  ],
});
