import { defineConfig } from '@umijs/max';

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
    title: 'Portal',
    logo: 'https://preview.pro.ant.design/static/logo.f0355d39.svg',
    layout: 'mix',
    splitMenus: false,
    fixedHeader: true,
    fixSiderbar: true,
    contentWidth: 'Fluid',
  },
  model: {},
  request: {},
  // Umi MFSU currently generates an invalid remote module for antd/reset.css
  // in development, causing the whole application to fail before React mounts.
  mfsu: false,
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
      path: '/set-password',
      component: '@/pages/SetPassword',
      layout: false,
    },
    {
      path: '/wx/diagnosis/:reportId',
      component: '@/pages/Wx/DiagnosisDetail',
      layout: false,
      hideInMenu: true,
    },
    {
      path: '/dashboard',
      name: '仪表盘',
      icon: 'DashboardOutlined',
      routes: [

        {
          path: '/dashboard/health',
          name: '健康总览',
          component: '@/pages/Dashboard/HealthDashboard',
        },
        {
          path: '/dashboard/monitoring',
          name: '异常设备',
          component: '@/pages/Dashboard/Monitoring',
        },
        {
          path: '/dashboard',
          redirect: '/dashboard/health',
        },
      ],
    },
    {
      path: '/data',
      name: '基础数据',
      icon: 'AppstoreOutlined',
      routes: [
        {
          path: '/data/suppliers',
          name: '合作厂商',
          component: '@/pages/Supplier',
        },
        {
          path: '/data/locations',
          name: '故障测点',
          component: '@/pages/Monitoring/Location',
        },
        {
          path: '/data/areas',
          name: '工作区域',
          component: '@/pages/Monitoring/Area',
        },
        {
          path: '/data/iso-standards',
          name: '国际标准',
          component: '@/pages/Monitoring/IsoStandard',
        },
        {
          path: '/data',
          redirect: '/data/suppliers',
        },
      ],
    },
    {
      path: '/process',
      name: '分组对比',
      icon: 'ClusterOutlined',
      routes: [
        {
          path: '/process/templates',
          name: '分组模板',
          component: '@/pages/Process/Template',
        },
        {
          path: '/process/manage',
          name: '分组设置',
          component: '@/pages/Process/Manage',
        },
        {
          path: '/process',
          redirect: '/process/templates',
        },
      ],
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
          path: '/device/bearings',
          name: '轴承型号',
          component: '@/pages/Device/Bearing',
        },
        {
          path: '/device/specs',
          name: '设备规格',
          component: '@/pages/Device/Spec',
        },
        {
          path: '/device/specs/:deviceSpecId/comparison',
          name: '同规格设备对比',
          component: '@/pages/Device/SpecComparison',
          hideInMenu: true,
        },
        {
          path: '/device/list',
          name: '实例列表',
          component: '@/pages/Device/List',
        },
        {
          path: '/device/:deviceId/health-archive',
          name: '设备健康档案',
          component: '@/pages/Device/HealthArchive',
          hideInMenu: true,
        },
        {
          path: '/device',
          redirect: '/device/categories',
        },
      ],
    },
    {
      path: '/monitoring',
      name: '监测设定',
      icon: 'RadarChartOutlined',
      routes: [
        {
          path: '/monitoring/sensors/batch-devices/:batchId',
          component: '@/pages/Monitoring/Sensors/BatchDevices',
          hideInMenu: true,
        },
        {
          path: '/monitoring/sensors/:sn/history',
          name: '历史趋势',
          component: '@/pages/Monitoring/Sensors/History/index',
          hideInMenu: true,
        },
        {
          path: '/monitoring/sensors',
          name: '设备批次',
          component: '@/pages/Monitoring/Sensors',
        },
        {
          path: '/monitoring/points',
          name: '测点设置',
          component: '@/pages/Monitoring/Points',
        },
        {
          path: '/monitoring/frequency',
          name: '监测频率',
          component: '@/pages/Monitoring/Frequency',
        },
        {
          path: '/monitoring/threshold',
          name: '阀值定义',
          component: '@/pages/Monitoring/Threshold',
        },
        {
          path: '/monitoring',
          redirect: '/monitoring/sensors',
        },
      ],
    },
    {
      path: '/org',
      name: '组织机构',
      icon: 'TeamOutlined',
      routes: [
        {
          path: '/org/tenant',
          name: '公司信息',
          component: '@/pages/Org/Tenant',
        },
        {
          path: '/org/departments',
          name: '部门资料',
          component: '@/pages/Org/Departments',
        },
        {
          path: '/org/employees',
          name: '员工资料',
          component: '@/pages/Org/Employees',
        },
        {
          path: '/org/users',
          name: '系统用户',
          component: '@/pages/Org/SystemUsers',
        },
        {
          path: '/org',
          redirect: '/org/tenant',
        },
      ],
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
      redirect: '/dashboard/health',
    },
  ],
});
