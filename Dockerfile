# 智能财务 Agent 平台镜像
FROM python:3.13-slim

# 时区设成中国，否则账目日期会差 8 小时
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 依赖单独一层：代码改了不用重装依赖，构建快很多
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制代码与脚本（脚本里有数据生成器，容器里也要能跑）
COPY app ./app
COPY scripts ./scripts

# 数据目录：账本 SQLite、向量库、凭证附件都存在这（compose 会挂载到宿主机）
RUN mkdir -p /app/data

# 非 root 用户运行——容器里用 root 是安全大忌
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 健康检查用 python 自带的 urllib（slim 镜像里没有 curl）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request as u, sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
