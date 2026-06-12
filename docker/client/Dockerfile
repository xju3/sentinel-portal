ARG NODE_IMAGE=node:22-alpine
ARG NGINX_IMAGE=nginx:1.27-alpine

FROM ${NODE_IMAGE} AS builder

ARG APP_NAME
ARG NPM_REGISTRY=https://registry.npmmirror.com

WORKDIR /app

COPY client/${APP_NAME}/package*.json ./
RUN npm ci --registry=${NPM_REGISTRY}

COPY client/${APP_NAME}/ .
RUN npm run build

FROM ${NGINX_IMAGE}

COPY docker/client/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
