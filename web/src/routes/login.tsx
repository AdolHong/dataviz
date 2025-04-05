import { createFileRoute } from '@tanstack/react-router';
import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import CryptoJS from 'crypto-js';
import { axiosInstance } from '@/lib/axios';

export const Route = createFileRoute('/login')({
  component: Login,
});

function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    try {
      // 使用CryptoJS加密密码
      const hashedPassword = CryptoJS.SHA256(password).toString();

      // 发送登录请求
      const response = await axiosInstance.post('/auth/login', {
        username,
        password: hashedPassword,
      });

      // 保存token到sessionStorage
      sessionStorage.setItem('auth-token', response.data.token);
      sessionStorage.setItem('auth-username', username);

      // 登录成功，跳转到主页
      navigate({ to: '/' });
    } catch (err: any) {
      setError(err.response?.data?.message || '登录失败，请检查用户名和密码');
    }
  };

  return (
    <div className='flex min-h-screen items-center justify-center bg-gray-100'>
      <div className='w-full max-w-md rounded-lg bg-white p-8 shadow-md'>
        <h2 className='mb-6 text-center text-2xl font-bold text-gray-800'>
          登录系统
        </h2>

        {error && (
          <div className='mb-4 rounded bg-red-100 p-3 text-red-700'>
            {error}
          </div>
        )}

        <form onSubmit={handleLogin}>
          <div className='mb-4'>
            <label
              htmlFor='username'
              className='mb-2 block text-sm font-medium text-gray-700'
            >
              用户名
            </label>
            <input
              id='username'
              type='text'
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className='w-full rounded-md border border-gray-300 px-3 py-2 focus:border-blue-500 focus:outline-none'
              required
            />
          </div>

          <div className='mb-6'>
            <label
              htmlFor='password'
              className='mb-2 block text-sm font-medium text-gray-700'
            >
              密码
            </label>
            <input
              id='password'
              type='password'
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className='w-full rounded-md border border-gray-300 px-3 py-2 focus:border-blue-500 focus:outline-none'
              required
            />
          </div>

          <button
            type='submit'
            className='w-full rounded-md bg-blue-600 py-2 text-white transition-colors hover:bg-blue-700 focus:outline-none'
          >
            登录
          </button>
        </form>
      </div>
    </div>
  );
}
