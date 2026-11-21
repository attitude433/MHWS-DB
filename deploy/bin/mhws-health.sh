#!/bin/bash
# mhws-health.sh — 5분마다 봇 상태 점검, 상태 변경 시 1:1 카톡 알림
ENV_FILE=/home/ubuntu/mhws-bot/.env
STATE_FILE=/home/ubuntu/mhws-bot/.health-state

ALERT_ROOM_ID=""
if [ -f "$ENV_FILE" ]; then
    ALERT_ROOM_ID=$(grep -E "^ALERT_ROOM_ID=" "$ENV_FILE" | cut -d= -f2)
fi

BOT=$(systemctl is-active mhws-bot.service 2>/dev/null || echo dead)
IRIS=$(systemctl is-active mhws-iris.service 2>/dev/null || echo dead)
DOCKER=$(sudo docker inspect --format='{{.State.Status}}' redroid 2>/dev/null || echo dead)

if [ "$BOT" = "active" ] && [ "$IRIS" = "active" ] && [ "$DOCKER" = "running" ]; then
    CUR=ok
else
    CUR="bot=$BOT iris=$IRIS redroid=$DOCKER"
fi

PREV=$(cat "$STATE_FILE" 2>/dev/null || echo unknown)

send_alert() {
    local msg="$1"
    if [ -z "$ALERT_ROOM_ID" ] || [ "$DOCKER" != "running" ]; then
        return
    fi
    curl -s -X POST http://127.0.0.1:3000/reply \
        -H "Content-Type: application/json" \
        -d "{\"type\":\"text\",\"room\":\"$ALERT_ROOM_ID\",\"data\":\"$msg\"}" >/dev/null 2>&1
}

if [ "$CUR" != "$PREV" ]; then
    NOW=$(TZ='Asia/Seoul' date +'%F %T')
    if [ "$CUR" = "ok" ]; then
        # 첫 실행 (PREV=unknown)엔 회복 알림 안 보냄
        if [ "$PREV" != "unknown" ]; then
            send_alert "✅ 다이애나 정상 회복 ($NOW KST)"
        fi
    else
        send_alert "🚨 다이애나 상태 이상: $CUR ($NOW KST)"
    fi
fi

echo "$CUR" > "$STATE_FILE"
