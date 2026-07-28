#!/bin/bash
# Mosquitto MQTT 브로커 설치
sudo apt-get update
sudo apt-get install -y mosquitto mosquitto-clients

# 설정 파일
sudo bash -c 'cat &gt; /etc/mosquitto/mosquitto.conf &lt;&lt; EOF
listener 1883
allow_anonymous true
log_dest file /var/log/mosquitto/mosquitto.log
EOF'

# 자동 시작 설정
sudo systemctl enable mosquitto
sudo systemctl start mosquitto

echo "MQTT 브로커 설치 완료"
echo "테스트: mosquitto_sub -h localhost -t peakbridge/# -v"
