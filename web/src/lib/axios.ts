import axios from 'axios';

// 个人mac
// export const BASE_URL = 'http://localhost:8080/api';

// 公司服务器
export const BASE_URL = '/api';

export const axiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 120000, // 两分钟超时
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
axiosInstance.interceptors.request.use(
  (config) => {
    // 从sessionStorage获取auth-token
    const token = localStorage.getItem('auth-token');
    const username = localStorage.getItem('auth-username');

    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }

    // 如果有用户名，添加到请求头中
    if (username) {
      config.headers['X-Username'] = username;
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
axiosInstance.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // 对响应错误做些什么
    console.error('API Error:', error);

    // 如果响应状态码是401（未授权），可能是token过期或无效
    if (error.response && error.response.status === 401) {
      // 清除sessionStorage中的token和username
      localStorage.removeItem('auth-token');
      localStorage.removeItem('auth-username');

      // 重定向到登录页面
      window.location.href = '/login';
    }

    return Promise.reject(error);
  }
);
