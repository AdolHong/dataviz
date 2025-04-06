# 使用Node.js官方镜像
FROM node:23-alpine

# 设置工作目录
WORKDIR /app

# 复制package.json和yarn.lock
COPY package*.json ./

# 安装依赖
RUN npm install --force

# 复制所有源代码
COPY . .

# 暴露开发服务器端口
EXPOSE 8080

# 启动开发服务器
CMD ["npm", "start"] 
