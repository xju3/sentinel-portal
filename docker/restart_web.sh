#!/bin/bash

# 这是一个用于重启前端 Web 应用 (portal 和 admin) 的脚本。
# 它会执行以下操作：
# 1. 停止并删除 'portal' 和 'admin' 容器。
# 2. 删除旧的 'portal' 和 'admin' 镜像，以确保下次启动时会重新构建。
# 3. 重新构建并以分离模式（-d）启动 'portal' 和 'admin' 服务，其他服务不受影响。

# 设置 -e 选项，如果任何命令返回非零退出状态，脚本将立即退出。
set -e

# 切换到脚本所在的目录，以确保 docker-compose 命令能找到 yml 文件。
cd "$(dirname "$0")"

echo "🛑 停止并删除 'portal' 和 'admin' 容器..."
# 'docker-compose stop' 停止服务
# 'docker-compose rm -f' 强制删除已停止的容器
docker-compose stop portal admin
docker-compose rm -f portal admin

echo "🗑️  正在删除旧的 Web 应用镜像..."
# 使用 'docker-compose images -q' 可以精确找到服务对应的镜像ID并删除
# '|| true' 确保在镜像不存在时脚本不会因错误而停止
docker rmi $(docker-compose images -q portal admin) 2>/dev/null || true

echo "✅ 旧镜像清理完毕。"

echo "🚀 重新构建并启动 'portal' 和 'admin' 服务..."
# 'docker-compose up' 加上服务名称，将只操作指定的这些服务。
# '--build' 强制重新构建镜像。
# '-d' 使容器在后台运行。
# '--force-recreate' 确保即使配置没有变化，容器也会被重建。
docker-compose up --build --force-recreate -d portal admin

echo "🎉 'portal' 和 'admin' 服务已成功启动！"