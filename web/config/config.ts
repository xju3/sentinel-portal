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
    title: 'Portal',
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
      path: '/register',
      component: '@/pages/Register',
      layout: false,
    },
    {
      path: '/device',
      name: '设备管理',
      icon: 'AppstoreOutlined',
      routes: [
        {
          path: '/device/categories',
          name: '设备分类',
          component: '@/pages/Device/Category',
        },
        {
          path: '/device/specs',
          name: '设备规格',
          component: '@/pages/Device/Spec',
        },
        {
          path: '/device/list',
          name: '设备列表',
          component: '@/pages/Device/List',
        },
        {
          path: '/device',
          redirect: '/device/categories',
        },
      ],
    },
    {
      path: '/process',
      name: '生产工艺',
      icon: 'ClusterOutlined',
      routes: [
        {
          path: '/process/templates',
          name: '工段模板',
          component: '@/pages/Process/Template',
        },
        {
          path: '/process/manage',
          name: '工段管理',
          component: '@/pages/Process/Manage',
        },
        {
          path: '/process',
          redirect: '/process/templates',
        },
      ],
    },
    {
      path: '/monitoring',
      name: '监测管理',
      icon: 'RadarChartOutlined',
      routes: [
        {
          path: '/monitoring/sensors',
          name: '传感器',
          component: '@/pages/Monitoring/Sensors',
        },
        {
          path: '/monitoring/points',
          name: '测点设置',
          component: '@/pages/Monitoring/Points',
        },
        {
          path: '/monitoring',
          redirect: '/monitoring/sensors',
        },
      ],
    },
    {
      path: '/welcome',
      name: 'Welcome',
      hideInMenu: true,
      component: '@/pages/Welcome',
    },
    {
      path: '/profile',
      hideInMenu: true,
      component: '@/pages/Profile',
    },
    {
      path: '/change-password',
      hideInMenu: true,
      component: '@/pages/ChangePassword',
    },
    {
      path: '/',
      redirect: '/device/categories',
    },
  ],
});
