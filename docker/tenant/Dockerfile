ARG NODE_IMAGE=node:22-alpine
ARG NGINX_IMAGE=nginx:1.27-alpine

FROM ${NODE_IMAGE} AS builder

WORKDIR /app

COPY web/tenant/package.json ./
RUN npm install

COPY web/tenant/ .
RUN npm run build

FROM ${NGINX_IMAGE}

COPY docker/tenant/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
