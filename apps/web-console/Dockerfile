FROM node:22-alpine AS build

WORKDIR /app

ARG VITE_CONTROL_PLANE_API_URL=http://localhost:8000
ARG VITE_RAG_SERVICE_URL=http://localhost:8002
ARG VITE_DEFAULT_TENANT_ID=payer-demo
ENV VITE_CONTROL_PLANE_API_URL=$VITE_CONTROL_PLANE_API_URL \
    VITE_RAG_SERVICE_URL=$VITE_RAG_SERVICE_URL \
    VITE_DEFAULT_TENANT_ID=$VITE_DEFAULT_TENANT_ID

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
