# DataViz 前端应用部署指南

这个仓库包含 DataViz 前端应用和用于 Docker 部署的配置文件。

## 文件结构

- `web/` - 前端应用源代码
- `web/Dockerfile` - 前端应用的 Docker 构建文件
- `web/nginx.conf` - Nginx 服务器配置
- `docker-compose.yml` - Docker Compose 配置文件

## 打包和启动 Docker 容器

### 方法 1：仅构建和运行前端容器

```bash
# 构建前端Docker镜像
cd web
docker build -t dataviz-frontend .

# 运行前端容器
docker run -p 80:80 dataviz-frontend
```

### 方法 2：使用 Docker Compose（推荐）

```bash
# 在项目根目录运行
docker-compose up -d frontend
```

如果要构建后端和数据库服务，请取消注释 docker-compose.yml 中相应的部分，并运行：

```bash
docker-compose up -d
```

## 访问应用

构建和运行容器后，您可以通过以下地址访问应用：

- 前端应用：http://localhost

## 开发环境

如果您需要在开发环境中运行，可以使用：

```bash
cd web
yarn install
yarn start
```

## 环境变量

- `VITE_API_BASE_URL` - API 基础 URL，在生产环境中设置为`/api`
