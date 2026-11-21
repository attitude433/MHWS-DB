# 서버 운영 설정 (오라클 `ssh oci-server`)

서버에 실제로 깔려 있는 파일을 2026-11-21 에 그대로 복사해 둔 것. 비밀값은 전부 서버 `~/mhws-bot/.env` 에만 있음 (여기엔 없음).

| 여기 | 서버 위치 | 역할 |
|---|---|---|
| `systemd/mhws-bot.service` | `/etc/systemd/system/mhws-bot.service` | 봇 본체 (`main.py`), 로그 `~/mhws-bot/bot.log` |
| `systemd/mhws-bot.web-port.conf` | `/etc/systemd/system/mhws-bot.service.d/web-port.conf` | 웹을 `127.0.0.1:8085` 로 (nginx 가 앞단) |
| `systemd/mhws-iris.service` | `/etc/systemd/system/mhws-iris.service` | redroid 부팅 대기 → adb 연결 → Iris 기동 |
| `bin/mhws-iris-wait.sh`, `bin/mhws-iris-start.sh` | `/usr/local/bin/` | 위 서비스가 부르는 스크립트 |
| `bin/mhws-health.sh` | `/usr/local/bin/` | cron 5분마다 상태 점검, 바뀌면 운영자 1:1 방 알림 |
| `bin/mhws-daily-report.py` | `/usr/local/bin/` | cron 매일 0시 API 사용량 보고 |
| `nginx/mhws.conf` | `/etc/nginx/sites-available/split.conf` 의 기본 서버 블록 | `mhws.diana.ai.kr` → 8085 |
| `iris/iris_control` | `~/iris/iris_control` | Iris 설치·시작·중지 도구 |

- redroid 컨테이너: `redroid/redroid:13.0.0_64only-latest`, 데이터 `~/redroid-data:/data`, adb `localhost:5555`, Iris HTTP `127.0.0.1:3000`
- cron (ubuntu): `*/5 * * * * mhws-health.sh`, `0 0 * * * mhws-daily-report.py >> /var/log/mhws-daily-report.log`

## 코드 올리기

```bash
scp commands/web.py oci-server:~/mhws-bot/commands/web.py
ssh oci-server 'sudo systemctl restart mhws-bot'   # 봇이 10초쯤 응답 안 함
```
