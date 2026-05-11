#!/bin/bash
# 自动提交并推送到 GitHub
MSG=${1:-"auto: $(date '+%Y-%m-%d %H:%M:%S') 阶段性保存"}
cd /workspace/nodeops
git add -A
git commit -m "$MSG" 2>&1 || echo "[已是最新，无需提交]"
git push origin main 2>&1 && echo "✅ 推送成功" || echo "❌ 推送失败"
