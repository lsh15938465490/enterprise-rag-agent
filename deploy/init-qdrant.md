# Qdrant 由 docker-compose 的 `qdrant` 服务自动启动。

# 知识库 collection 不要手工创建：步骤 8 会在创建知识库时按
# `kb_{tenant_slug}_{kb_id_nodash}` 自动 `create_collection`。

# 本机检查：
#   curl http://localhost:6333/readyz
