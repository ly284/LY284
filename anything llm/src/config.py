from pydantic_settings import BaseSettings


class Config(BaseSettings):
    anythingllm_base_url: str = "http://localhost:3001"
    # API key 只从环境变量 / .env 注入，不提供默认值；缺失时启动即报错
    anythingllm_api_key: str = ""
    anythingllm_default_workspace: str = ""
    mcp_server_port: int = 8000
    mcp_server_host: str = "0.0.0.0"

    class ConfigDict:
        env_file = ".env"
        env_file_encoding = "utf-8"


config = Config()

if not config.anythingllm_api_key.strip():
    raise SystemExit(
        "缺少 ANYTHINGLLM_API_KEY 配置：请复制 .env.example 为 .env，"
        "填写你的 AnythingLLM API Key 后重新启动（密钥不要提交到仓库）"
    )
