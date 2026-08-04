#!/bin/bash

# 显示当前目录下的 Docker Compose 项目日志占用情况
echo "=== 清理前的 Docker Compose 日志大小 ==="
docker compose ps -q | xargs -I {} docker inspect --format='{{.LogPath}}' {} 2>/dev/null | xargs du -sh 2>/dev/null

echo ""
read -p "确认要清空以上容器的日志吗？(y/N): " confirm

if [[ "$confirm" =~ ^[Yy]$ ]]; then
    echo "开始清理日志..."

    # 遍历当前 docker-compose 项目中的所有容器并清空日志
    for container_id in $(docker compose ps -q); do
        log_path=$(docker inspect --format='{{.LogPath}}' "$container_id" 2>/dev/null)
        if [ -n "$log_path" ] && [ -f "$log_path" ]; then
            # 使用 truncate 清空日志文件，不占用额外的磁盘空间，容器无需重启
            sudo truncate -s 0 "$log_path"
            echo "已清空容器: $(docker inspect --format='{{.Name}}' "$container_id") -> 日志路径: $log_path"
        fi
    done

    echo "=== 清理完成！清理后的日志大小 ==="
    docker compose ps -q | xargs -I {} docker inspect --format='{{.LogPath}}' {} 2>/dev/null | xargs du -sh 2>/dev/null
else
    echo "操作已取消。"
fi
~                                                                                                                                                                      
~              