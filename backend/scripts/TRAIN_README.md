# PeakBridge RL 학습 가이드

## 설치
```bash
git clone https://github.com/Weierstrass2/peakbridge
cd peakbridge/backend
pip install -r requirements.txt
pip install ev2gym stable-baselines3 optuna
```

## 실행 순서
```bash
python scripts/collect_weather_data.py
python scripts/convert_to_ev2gym.py
python scripts/train_ev2gym_ppo.py
```

## 주의사항
- 학습 중 컴퓨터 끄면 안 됨
- 100,000 스텝마다 자동 저장됨
- 중단 후 재시작 가능

## 완료 후
```bash
git add models/
git commit -m "PPO 5,000,000 스텝 학습 완료"
git push origin main
```
