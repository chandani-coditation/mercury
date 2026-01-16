import os
import sys

def get_secret(name: str, required=True):
    value = os.getenv(name)
    if required and not value:
        print(f"❌ Missing required secret: {name}")
        sys.exit(1)
    return value

def main():
    api_key = get_secret("API_KEY")
    db_password = get_secret("DB_PASSWORD")

    print("✅ Secrets loaded successfully")
    print(f"API_KEY length: {len(api_key)}")
    print(f"DB_PASSWORD length: {len(db_password)}")

if __name__ == "__main__":
    main()
