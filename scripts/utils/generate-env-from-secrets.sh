#!/bin/bash

# Generate .env file from GitHub Secrets based on environment
# Usage: ./generate-env-from-secrets.sh <environment>

set -euo pipefail

ENVIRONMENT="${1:-np}"
ENV_FILE="${ENV_FILE:-.env.github}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Generating .env file for environment: ${ENVIRONMENT}${NC}"

get_secret() {
    local var_name="$1"
    local value="${!var_name:-}"
    echo "$value"
}

write_env_var() {
    local var_name="$1"
    local value="$2"
    local default_value="${3:-}"
    
    if [ -n "$value" ]; then
        echo "${var_name}=${value}" >> "$ENV_FILE"
    elif [ -n "$default_value" ]; then
        echo "${var_name}=${default_value}" >> "$ENV_FILE"
    fi
}

rm -f "$ENV_FILE"

echo "# Database Configuration" >> "$ENV_FILE"
echo "# Generated from GitHub Secrets for environment: ${ENVIRONMENT}" >> "$ENV_FILE"
echo "# Generated at: $(date -u +"%Y-%m-%d %H:%M:%S UTC")" >> "$ENV_FILE"
echo "" >> "$ENV_FILE"

write_env_var "POSTGRES_HOST" "$(get_secret 'POSTGRES_HOST')" "postgres"
write_env_var "POSTGRES_PORT" "$(get_secret 'POSTGRES_PORT')" "5432"
write_env_var "POSTGRES_DB" "$(get_secret 'POSTGRES_DB')" "nocdb"
write_env_var "POSTGRES_USER" "$(get_secret 'POSTGRES_USER')" "noc_ai"
write_env_var "POSTGRES_PASSWORD" "$(get_secret 'POSTGRES_PASSWORD')"

if [ -z "$(get_secret 'POSTGRES_PASSWORD')" ]; then
    echo -e "${RED}Error: POSTGRES_PASSWORD secret is required but not set${NC}"
    exit 1
fi

echo "" >> "$ENV_FILE"
echo "# LLM Configuration" >> "$ENV_FILE"

OPENAI_KEY=$(get_secret 'OPENAI_API_KEY')
if [ -n "$OPENAI_KEY" ]; then
    write_env_var "OPENAI_API_KEY" "$OPENAI_KEY"
fi

PRIVATE_GATEWAY=$(get_secret 'PRIVATE_LLM_GATEWAY')
if [ -n "$PRIVATE_GATEWAY" ]; then
    write_env_var "PRIVATE_LLM_GATEWAY" "$PRIVATE_GATEWAY"
else
    write_env_var "PRIVATE_LLM_GATEWAY" "false"
fi

write_env_var "PRIVATE_LLM_GATEWAY_URL" "$(get_secret 'PRIVATE_LLM_GATEWAY_URL')"
write_env_var "PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL" "$(get_secret 'PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL')"
write_env_var "PRIVATE_LLM_AUTH_KEY" "$(get_secret 'PRIVATE_LLM_AUTH_KEY')"
write_env_var "PRIVATE_LLM_CERT_PATH" "$(get_secret 'PRIVATE_LLM_CERT_PATH')"

echo "" >> "$ENV_FILE"
echo "# Service Configuration" >> "$ENV_FILE"

write_env_var "INGESTION_SERVICE_HOST" "$(get_secret 'INGESTION_SERVICE_HOST')" "0.0.0.0"
write_env_var "INGESTION_SERVICE_PORT" "$(get_secret 'INGESTION_SERVICE_PORT')" "8002"
write_env_var "AI_SERVICE_HOST" "$(get_secret 'AI_SERVICE_HOST')" "0.0.0.0"
write_env_var "AI_SERVICE_PORT" "$(get_secret 'AI_SERVICE_PORT')" "8001"

echo "" >> "$ENV_FILE"
echo "# Frontend Configuration" >> "$ENV_FILE"

write_env_var "VITE_API_BASE_URL" "$(get_secret 'VITE_API_BASE_URL')" "http://localhost:8001/api/v1"

echo "" >> "$ENV_FILE"
echo "# CORS Configuration" >> "$ENV_FILE"

write_env_var "CORS_ALLOWED_ORIGINS" "$(get_secret 'CORS_ALLOWED_ORIGINS')" "http://localhost:5173"

echo "" >> "$ENV_FILE"
echo "# Logging and Database Pool Configuration" >> "$ENV_FILE"

write_env_var "LOG_LEVEL" "$(get_secret 'LOG_LEVEL')" "INFO"
write_env_var "DB_POOL_MIN" "$(get_secret 'DB_POOL_MIN')" "5"
write_env_var "DB_POOL_MAX" "$(get_secret 'DB_POOL_MAX')" "20"
write_env_var "DB_POOL_WAIT_TIMEOUT" "$(get_secret 'DB_POOL_WAIT_TIMEOUT')" "30"

echo -e "${GREEN}Successfully generated ${ENV_FILE} for ${ENVIRONMENT} environment${NC}"
