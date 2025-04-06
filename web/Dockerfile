# 第一阶段：构建应用
FROM node:20-alpine AS build

# 设置工作目录
WORKDIR /app

# 复制 package.json 和 package-lock.json
COPY package*.json ./
COPY yarn.lock ./

# 安装依赖
RUN yarn install

# 复制源代码
COPY . .

# 构建应用
RUN yarn build

# 第二阶段：生产环境
FROM nginx:alpine

# 拷贝构建产物到nginx
COPY --from=build /app/dist /usr/share/nginx/html

# 拷贝nginx配置文件
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 暴露80端口
EXPOSE 80

# 启动nginx
CMD ["nginx", "-g", "daemon off;"] 