# 前端镜像：Node 构建静态资源，Nginx 托管并反向代理 /api
FROM node:20-alpine AS build

WORKDIR /app

# 先装依赖，利用镜像层缓存
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

# 站点配置：SPA 路由回退 + /api 反向代理（含 SSE 不缓冲）
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
