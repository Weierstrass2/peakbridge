from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import ev2gym
from ev2gym.models.ev2gym_env import EV2Gym
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
from stable_baselines3.common.env_util import make_vec_env


print("=" * 50)
print("PeakBridge PPO 학습 시작")
print(f"시작: {datetime.now()}")
print("=" * 50)

ev2gym_path = os.path.dirname(ev2gym.__file__)
config_file = os.path.join(ev2gym_path, "example_config_files", "PublicPST.yaml")
os.chdir(ev2gym_path)  # EV2Gym 데이터 파일 찾을 수 있게 작업 디렉토리 변경

print(f"Config: {config_file}")
print(f"작업 디렉토리: {os.getcwd()}")

Path("models").mkdir(exist_ok=True)
Path("models/best").mkdir(parents=True, exist_ok=True)
Path("logs").mkdir(exist_ok=True)


def make_env():
    return EV2Gym(config_file=config_file)


n_envs = 4
env = make_vec_env(make_env, n_envs=n_envs)
eval_env = make_vec_env(make_env, n_envs=1)

checkpoint_callback = CheckpointCallback(
    save_freq=100000,
    save_path="./models/",
    name_prefix="ppo_peakbridge",
)

eval_callback = EvalCallback(
    eval_env,
    best_model_save_path="./models/best/",
    log_path="./logs/",
    eval_freq=50000,
    n_eval_episodes=10,
    verbose=1,
)

model = PPO(
    "MlpPolicy",
    env,
    learning_rate=3e-4,
    n_steps=2048,
    batch_size=64,
    n_epochs=10,
    gamma=0.99,
    gae_lambda=0.95,
    clip_range=0.2,
    verbose=1,
    tensorboard_log="./logs/",
)

print("학습 시작: 5,000,000 스텝")
print(f"병렬 환경: {n_envs}개")
print("GPU 있으면 약 1일")
print("CPU만 있으면 약 5~7일")
print("100,000 스텝마다 자동 저장\n")

model.learn(
    total_timesteps=5000000,
    callback=[checkpoint_callback, eval_callback],
    progress_bar=True,
)

model.save("models/ppo_peakbridge_final")

print("\n" + "=" * 50)
print("학습 완료!")
print(f"완료: {datetime.now()}")
print("모델 저장: models/ppo_peakbridge_final.zip")
print("=" * 50)
print("\nGitHub에 올리기:")
print("git add models/")
print('git commit -m "PPO 5,000,000 스텝 학습 완료"')
print("git push origin main")
