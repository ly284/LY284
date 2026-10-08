from pydantic_settings import BaseSettings

class Config(BaseSettings):
    anythingllm_base_url: str = "http://localhost:3001"
    anythingllm_api_key: str = "KRY1Z4H-CPD4FFP-GEVVKDQ-Y0RF4WJ"
    anythingllm_default_workspace: str = ""
    mcp_server_port: int = 8000
    mcp_server_host: str = "0.0.0.0"

    class ConfigDict:
        env_file = ".env"
        env_file_encoding = "utf-8"

config = Config()