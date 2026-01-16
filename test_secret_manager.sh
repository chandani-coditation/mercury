#!/bin/bash

echo "Script started..."

if [ -z "$MY_SECRET_KEY" ]; then
  echo "❌ Secret is NOT available"
else
  echo "✅ Secret is available"
  echo "Secret length: ${#MY_SECRET_KEY}"
fi
