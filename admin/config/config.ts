import { defineConfig } from '@umijs/max';

export default defineConfig({
  npmClient: 'npm',
  antd: {},
  proxy: {
    '/api': {
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
      path: '/tenant',
      name: '租户',
      icon: 'TeamOutlined',
      component: '@/pages/Tenant',
    },
    {
      path: '/sensor',
      name: '传感器',
      icon: 'RadarChartOutlined',
      routes: [
        {
          path: '/sensor/type',
          name: '型号',
          component: '@/pages/Sensor/Type',
        },
        {
          path: '/sensor/batch',
          name: '批次',
          component: '@/pages/Sensor/Batch',
        },
        {
          path: '/sensor/product',
          name: '产品',
          component: '@/pages/Sensor/Product',
        },
        {
          path: '/sensor',
          redirect: '/sensor/type',
        },
      ],
    },
    {
      path: '/',
      redirect: '/login',
    },
  ],
});
