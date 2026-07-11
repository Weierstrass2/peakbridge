"""torch 없이 SB3 PPO zip에서 MlpPolicy 가중치를 numpy로 로드."""
import io
import json
import pickle
import zipfile
import numpy as np

DTYPES = {
    "FloatStorage": np.float32,
    "DoubleStorage": np.float64,
    "LongStorage": np.int64,
    "IntStorage": np.int32,
}


class _FakeTensor:
    def __init__(self, storage, offset, size, stride):
        arr = storage[offset: offset + int(np.prod(size))] if len(size) else storage[offset:offset + 1]
        self.array = np.lib.stride_tricks.as_strided(
            storage[offset:], shape=tuple(size),
            strides=tuple(s * storage.itemsize for s in stride),
        ).copy() if size else arr.copy()


def _rebuild_tensor_v2(storage, offset, size, stride, *args):
    return _FakeTensor(storage, offset, size, stride).array


class _Unpickler(pickle.Unpickler):
    def __init__(self, f, zf, prefix):
        super().__init__(f)
        self.zf = zf
        self.prefix = prefix

    def find_class(self, module, name):
        if name == "_rebuild_tensor_v2":
            return _rebuild_tensor_v2
        if "Storage" in name:
            return name  # 스토리지 타입명을 문자열로
        if module == "collections" and name == "OrderedDict":
            from collections import OrderedDict
            return OrderedDict
        # 그 외 torch 클래스는 더미
        return lambda *a, **k: None

    def persistent_load(self, pid):
        # ('storage', storage_type(str), key, location, numel)
        typ = pid[1] if isinstance(pid[1], str) else pid[1].__name__
        key, numel = pid[2], pid[4]
        dtype = DTYPES.get(typ, np.float32)
        raw = self.zf.read(f"{self.prefix}/data/{key}")
        return np.frombuffer(raw, dtype=dtype)


def load_state_dict(sb3_zip_path):
    """SB3 zip → policy.pth state_dict (numpy dict)."""
    with zipfile.ZipFile(sb3_zip_path) as outer:
        pth = outer.read("policy.pth")
    with zipfile.ZipFile(io.BytesIO(pth)) as zf:
        names = zf.namelist()
        pkl_name = [n for n in names if n.endswith("data.pkl")][0]
        prefix = pkl_name.rsplit("/", 1)[0]
        up = _Unpickler(io.BytesIO(zf.read(pkl_name)), zf, prefix)
        return dict(up.load())


class NumpyPPOPolicy:
    """SB3 MlpPolicy (Box action) deterministic forward."""

    def __init__(self, sb3_zip_path):
        sd = load_state_dict(sb3_zip_path)
        self.pi_layers = []
        i = 0
        while f"mlp_extractor.policy_net.{i}.weight" in sd:
            self.pi_layers.append(
                (sd[f"mlp_extractor.policy_net.{i}.weight"], sd[f"mlp_extractor.policy_net.{i}.bias"])
            )
            i += 2
        self.action_w = sd["action_net.weight"]
        self.action_b = sd["action_net.bias"]
        self.keys = list(sd.keys())

    def predict(self, obs):
        x = np.asarray(obs, dtype=np.float32).ravel()
        for w, b in self.pi_layers:
            x = np.tanh(w @ x + b)
        return self.action_w @ x + self.action_b


if __name__ == "__main__":
    import sys
    p = NumpyPPOPolicy(sys.argv[1])
    print("layers:", [w.shape for w, _ in p.pi_layers], "action:", p.action_w.shape)
    print("keys:", p.keys)
