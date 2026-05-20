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
      path: '/tenant',
      name: '租户',
      icon: 'TeamOutlined',
      component: '@/pages/Tenant',
    },
    {
      path: '/device',
      name: '设备',
      icon: 'AppstoreOutlined',
      routes: [
        {
          path: '/device/spec',
          name: '型号',
          component: '@/pages/Device/Spec',
        },
        {
          path: '/device',
          redirect: '/device/spec',
        },
      ],
    },
    {
      path: '/sensor',
      name: '传感器',
      icon: 'RadarChartOutlined',
      component: '@/pages/Sensor',
    },
    {
      path: '/',
      redirect: '/tenant',
    },
  ],
});
