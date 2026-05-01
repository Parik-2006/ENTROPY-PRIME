"""
Entropy Prime — RL Governor + Per-User Biometric Profile Pre-Trainer

Trains:
  1. DQN Governor        — selects Argon2id hardness per request
  2. Per-User CNN1D      — fine-tunes shared backbone with per-user adapter
  3. Per-User Autoencoder — learns per-user behavioral manifold for drift detection
  4. Feature Selector    — learns per-user discriminative feature subset

Usage:
    python backend/train.py
    python backend/train.py --episodes 200000 --bot-ratio 0.35 --out checkpoints/governor.pt
    python backend/train.py --mode per_user --user-id usr_abc123 --samples 500
    python backend/train.py --mode all
"""
import argparse, os, time, json
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque

# ── Feature constants (matches biometrics.js + cnn1d.py) ─────────────────────
FEATURE_NAMES = [
    "dwell_norm", "flight_norm", "speed_norm", "jitter_norm",
    "accel_norm",  "rhythm_norm", "pause_norm",  "bigram_norm",
]
N_FEATURES = 8
SEQ_LEN    = 50
LATENT_DIM = 32

# ── Q-Network (DQN Governor) ──────────────────────────────────────────────────
class QNetwork(nn.Module):
    def __init__(self, s=3, a=4):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(s, 64), nn.ReLU(),
            nn.Linear(64, 64), nn.ReLU(),
            nn.Linear(64, a),
        )
    def forward(self, x): return self.net(x)

# ── Auth Environment ──────────────────────────────────────────────────────────
class AuthEnv:
    def __init__(self, bot_ratio=0.30):
        self.bot_ratio   = bot_ratio
        self.server_load = 0.4

    def _sample(self):
        is_bot = np.random.rand() < self.bot_ratio
        if is_bot:
            theta = np.clip(np.random.beta(1.5, 6), 0, 1)
            h_exp = np.clip(np.random.beta(2, 5),   0, 1)
        else:
            theta = np.clip(np.random.beta(6, 1.5), 0, 1)
            h_exp = np.clip(np.random.beta(4, 2),   0, 1)
        self.server_load = np.clip(self.server_load + np.random.normal(0, 0.05), 0.1, 0.95)
        return np.array([theta, h_exp, self.server_load], dtype=np.float32)

    def reset(self):
        self._s = self._sample(); return self._s

    def step(self, action):
        theta, h_exp, load = self._s
        is_bot    = theta < 0.3
        is_human  = theta > 0.7
        is_strong = h_exp > 0.6
        if   is_bot   and action >= 2:               reward =  2.0
        elif is_bot   and action <  2:               reward = -2.0
        elif is_human and is_strong and action == 0: reward =  1.0
        elif is_human and action == 3:               reward = -0.5
        elif load > 0.85:                            reward = -0.3 * (action + 1)
        else:                                        reward =  0.1
        self._s = self._sample()
        return self._s, float(reward), False

@dataclass
class Tr:
    s: np.ndarray; a: int; r: float; s2: np.ndarray; d: bool

class ReplayBuffer:
    def __init__(self, cap=20_000): self._b = deque(maxlen=cap)
    def push(self, t): self._b.append(t)
    def sample(self, n):
        idx = np.random.choice(len(self._b), n, replace=False)
        return [self._b[i] for i in idx]
    def __len__(self): return len(self._b)

# ── DQN Training ─────────────────────────────────────────────────────────────
def train_dqn(episodes=100_000, bot_ratio=0.30, out="checkpoints/governor.pt"):
    print(f"\n[DQN] Training RL Governor — {episodes:,} steps, bot_ratio={bot_ratio}")
    print("─" * 60)
    env = AuthEnv(bot_ratio)
    q   = QNetwork(); tq = QNetwork()
    tq.load_state_dict(q.state_dict()); tq.eval()
    opt = optim.Adam(q.parameters(), lr=1e-3)
    buf = ReplayBuffer()

    GAMMA=.99; EPS_START=1.; EPS_END=.05; EPS_DECAY=3000
    BATCH=64; TARGET_UPDATE=300

    s = env.reset()
    total_r, count = 0., 0
    t0 = time.time()

    for step in range(1, episodes + 1):
        eps = EPS_END + (EPS_START - EPS_END) * np.exp(-step / EPS_DECAY)
        if np.random.rand() < eps:
            a = np.random.randint(4)
        else:
            with torch.no_grad():
                a = int(q(torch.tensor(s, dtype=torch.float32).unsqueeze(0)).argmax(1).item())

        s2, r, done = env.step(a)
        buf.push(Tr(s, a, r, s2, done))
        total_r += r; count += 1; s = s2

        if len(buf) >= BATCH:
            batch = buf.sample(BATCH)
            S  = torch.tensor(np.stack([b.s  for b in batch]), dtype=torch.float32)
            A  = torch.tensor([b.a for b in batch], dtype=torch.long)
            R  = torch.tensor([b.r for b in batch], dtype=torch.float32)
            S2 = torch.tensor(np.stack([b.s2 for b in batch]), dtype=torch.float32)
            D  = torch.tensor([b.d for b in batch], dtype=torch.float32)
            qv = q(S).gather(1, A.unsqueeze(1)).squeeze()
            with torch.no_grad(): nq = tq(S2).max(1).values
            loss = nn.functional.smooth_l1_loss(qv, R + GAMMA * nq * (1 - D))
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(q.parameters(), 1.); opt.step()
            if step % TARGET_UPDATE == 0:
                tq.load_state_dict(q.state_dict())

        if step % 10_000 == 0:
            elapsed = time.time() - t0
            print(f"  step {step:>8,} / {episodes:,} "
                  f"| mean_reward {total_r/max(count,1):+.3f} "
                  f"| ε {eps:.3f} "
                  f"| buf {len(buf):,} "
                  f"| {elapsed:.0f}s elapsed")
            total_r, count = 0., 0

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    torch.save({"q_net": q.state_dict(), "steps": episodes}, out)
    print(f"✓ DQN checkpoint → {out}")

# ── Per-User Behavioral Simulator ─────────────────────────────────────────────
class UserBehaviorSimulator:
    """
    Simulates per-user behavioral typing/pointer patterns.
    Each 'user' has a fixed mean + noise profile for each feature.
    Drift injection creates a "session hijack" scenario.
    """
    def __init__(self, user_id: str, seed: int = None):
        rng = np.random.RandomState(seed or hash(user_id) % 2**32)
        # Per-user stable behavioral means [0,1] for each of 8 features
        self.means = rng.beta(4, 2, size=N_FEATURES).astype(np.float32)
        # Per-user noise std (some users are more consistent)
        self.stds  = rng.beta(2, 8, size=N_FEATURES).astype(np.float32) * 0.2
        self.user_id = user_id

    def sample_normal(self, n_samples: int = 1) -> np.ndarray:
        """Sample normal behavioral vectors for this user."""
        noise = np.random.randn(n_samples, N_FEATURES).astype(np.float32)
        samples = self.means[None, :] + self.stds[None, :] * noise
        return np.clip(samples, 0, 1)  # [n_samples, N_FEATURES]

    def sample_drifted(self, n_samples: int = 1, drift_factor: float = 3.0) -> np.ndarray:
        """Sample drifted (anomalous) behavioral vectors."""
        # Shift means substantially in random direction
        drift_means = np.clip(
            self.means + np.random.randn(N_FEATURES).astype(np.float32) * drift_factor * self.stds,
            0, 1
        )
        noise   = np.random.randn(n_samples, N_FEATURES).astype(np.float32)
        samples = drift_means[None, :] + self.stds[None, :] * noise * 2
        return np.clip(samples, 0, 1)

    def sample_sequence(self, n_samples: int = 1, drifted: bool = False) -> torch.Tensor:
        """
        Sample a full CNN input tensor: [n_samples, N_FEATURES, SEQ_LEN].
        Each sample is a sequence of per-timestep behavioral vectors.
        """
        data = np.zeros((n_samples, SEQ_LEN, N_FEATURES), dtype=np.float32)
        for i in range(n_samples):
            timesteps = self.sample_drifted(SEQ_LEN) if drifted else self.sample_normal(SEQ_LEN)
            data[i] = timesteps  # [SEQ_LEN, N_FEATURES]
        # Transpose to [n_samples, N_FEATURES, SEQ_LEN] for Conv1d
        return torch.FloatTensor(data.transpose(0, 2, 1))

    def get_flat_features(self, n_samples: int = 1, drifted: bool = False) -> np.ndarray:
        """Sample flat feature vectors [n_samples, N_FEATURES]."""
        return self.sample_drifted(n_samples) if drifted else self.sample_normal(n_samples)

# ── Shared CNN1D Training ─────────────────────────────────────────────────────
def train_shared_cnn(
    n_users: int = 50,
    samples_per_user: int = 200,
    epochs: int = 30,
    out: str = "checkpoints/cnn1d_shared.pt",
):
    """
    Train the shared CNN1D backbone on synthetic multi-user data.
    Task: binary classification (human=1 vs. bot=0) using 8-channel sequences.
    """
    print(f"\n[CNN1D] Training shared backbone — {n_users} users × {samples_per_user} samples")
    print("─" * 60)

    # Import here to avoid circular deps in deployment
    import sys; sys.path.insert(0, os.path.dirname(__file__))
    from models.cnn1d import CNN1D

    model = CNN1D(input_channels=N_FEATURES, out_dim=1, seq_len=SEQ_LEN)
    # Replace head with binary classifier
    model.head = nn.Sequential(nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1), nn.Sigmoid())
    optimizer  = optim.Adam(model.parameters(), lr=1e-3)
    criterion  = nn.BCELoss()

    # Synthetic dataset: human users + bot profiles
    X_list, y_list = [], []
    simulators = [UserBehaviorSimulator(f"usr_{i:04d}", seed=i) for i in range(n_users)]

    for sim in simulators:
        X_human = sim.sample_sequence(samples_per_user, drifted=False)
        X_bot   = sim.sample_sequence(samples_per_user // 4, drifted=True)
        X_list.extend([X_human, X_bot])
        y_list.extend([
            torch.ones(samples_per_user, 1),
            torch.zeros(samples_per_user // 4, 1),
        ])

    X = torch.cat(X_list, dim=0)
    y = torch.cat(y_list, dim=0)
    # Shuffle
    perm = torch.randperm(X.shape[0])
    X, y = X[perm], y[perm]

    BATCH = 64
    n_batches = len(X) // BATCH
    best_loss = float('inf')

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.
        for i in range(n_batches):
            xb = X[i*BATCH:(i+1)*BATCH]
            yb = y[i*BATCH:(i+1)*BATCH]
            out = model(xb)
            loss = criterion(out, yb)
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            epoch_loss += loss.item()
        epoch_loss /= n_batches
        if epoch_loss < best_loss:
            best_loss = epoch_loss
        if epoch % 5 == 0:
            print(f"  epoch {epoch:>3}/{epochs} | loss {epoch_loss:.4f} | best {best_loss:.4f}")

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    torch.save({"model": model.state_dict(), "epochs": epochs, "n_users": n_users}, out)
    print(f"✓ Shared CNN1D checkpoint → {out}")
    return model

# ── Per-User Autoencoder Training ─────────────────────────────────────────────
class Autoencoder(nn.Module):
    """Per-user autoencoder for behavioral drift detection."""
    def __init__(self, input_dim: int = N_FEATURES * SEQ_LEN, latent_dim: int = LATENT_DIM):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 256), nn.ReLU(),
            nn.Linear(256, 128),       nn.ReLU(),
            nn.Linear(128, 64),        nn.ReLU(),
            nn.Linear(64, latent_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 64),  nn.ReLU(),
            nn.Linear(64, 128),         nn.ReLU(),
            nn.Linear(128, 256),        nn.ReLU(),
            nn.Linear(256, input_dim),  nn.Sigmoid(),
        )

    def forward(self, x):
        z = self.encoder(x)
        return self.decoder(z)

    def encode(self, x):
        return self.encoder(x)

def train_per_user_autoencoder(
    user_id: str,
    n_normal_samples: int = 300,
    epochs: int = 50,
    out_dir: str = "checkpoints/users",
):
    """
    Train a per-user autoencoder on that user's behavioral pattern.
    The AE learns the user's normal manifold; high reconstruction error = drift.
    """
    print(f"\n[Autoencoder] Training for user={user_id}, samples={n_normal_samples}")

    sim   = UserBehaviorSimulator(user_id)
    input_dim = N_FEATURES * SEQ_LEN
    model     = Autoencoder(input_dim=input_dim, latent_dim=LATENT_DIM)
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.MSELoss()

    # Normal samples for training
    X_normal = torch.FloatTensor(sim.sample_normal(n_normal_samples)).view(n_normal_samples, -1)
    # Augment with slight variation
    X_augmented = X_normal + torch.randn_like(X_normal) * 0.02

    BATCH = 32
    best_loss = float('inf')

    for epoch in range(1, epochs + 1):
        model.train()
        perm    = torch.randperm(len(X_augmented))
        X_epoch = X_augmented[perm]
        epoch_loss = 0.
        for i in range(0, len(X_epoch), BATCH):
            xb = X_epoch[i:i+BATCH]
            if len(xb) < 2: continue
            out  = model(xb)
            loss = criterion(out, xb)
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            epoch_loss += loss.item()

        n_batches  = max(len(X_epoch) // BATCH, 1)
        epoch_loss /= n_batches
        if epoch_loss < best_loss:
            best_loss = epoch_loss

    # Compute baseline reconstruction error on normal samples
    model.eval()
    with torch.no_grad():
        recon    = model(X_normal)
        e_rec    = nn.functional.mse_loss(recon, X_normal, reduction='none')
        e_per    = e_rec.mean(dim=1).numpy()
        baseline = float(e_per.mean())
        threshold = float(e_per.mean() + 2 * e_per.std())

    os.makedirs(out_dir, exist_ok=True)
    ckpt_path = os.path.join(out_dir, f"{user_id}_autoencoder.pt")
    torch.save({
        "model":      model.state_dict(),
        "user_id":    user_id,
        "baseline":   baseline,
        "threshold":  threshold,
        "epochs":     epochs,
        "input_dim":  input_dim,
        "latent_dim": LATENT_DIM,
    }, ckpt_path)
    print(f"  ✓ baseline e_rec={baseline:.4f} | threshold={threshold:.4f} → {ckpt_path}")
    return model, baseline, threshold

# ── Feature Selector Training ─────────────────────────────────────────────────
def train_per_user_feature_selector(
    user_id: str,
    n_samples: int = 500,
    epochs: int = 100,
    k: int = 6,
    out_dir: str = "checkpoints/users",
):
    """
    Train a differentiable per-user feature selector.
    Learns which of the 8 biometric features are most discriminative for this user
    by training a small classifier (human vs. drifted) with L1 sparsity on selector.
    """
    print(f"\n[FeatureSelector] Training for user={user_id}")
    import sys; sys.path.insert(0, os.path.dirname(__file__))
    from models.cnn1d import FeatureSelector

    sim      = UserBehaviorSimulator(user_id)
    selector = FeatureSelector(n_features=N_FEATURES, k=k)

    # Simple linear probe on top of masked features
    probe    = nn.Sequential(nn.Linear(N_FEATURES, 16), nn.ReLU(), nn.Linear(16, 1), nn.Sigmoid())
    params   = list(selector.parameters()) + list(probe.parameters())
    optimizer = optim.Adam(params, lr=5e-3)
    criterion = nn.BCELoss()

    # Dataset: normal=1, drifted=0 (flat features, not sequences)
    X_normal  = torch.FloatTensor(sim.get_flat_features(n_samples, drifted=False))
    X_drifted = torch.FloatTensor(sim.get_flat_features(n_samples // 4, drifted=True))
    X = torch.cat([X_normal, X_drifted], dim=0)
    y = torch.cat([torch.ones(n_samples, 1), torch.zeros(n_samples // 4, 1)], dim=0)
    perm = torch.randperm(len(X)); X, y = X[perm], y[perm]

    BATCH = 32
    for epoch in range(1, epochs + 1):
        selector.train(); probe.train()
        perm_e  = torch.randperm(len(X))
        X_e, y_e = X[perm_e], y[perm_e]
        epoch_loss = 0.
        for i in range(0, len(X_e), BATCH):
            xb, yb = X_e[i:i+BATCH], y_e[i:i+BATCH]
            if len(xb) < 2: continue
            # Apply selector as channel mask on flat features
            mask    = torch.sigmoid(selector.logits).unsqueeze(0)  # [1, 8]
            x_masked = xb * mask                                    # [B, 8]
            out      = probe(x_masked)
            # BCE + L1 sparsity to encourage few active features
            loss = criterion(out, yb) + 0.01 * selector.logits.abs().mean()
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            epoch_loss += loss.item()

    selector.eval()
    state = selector.to_dict()
    print(f"  ✓ Selected features: {state['selected_names']}")

    os.makedirs(out_dir, exist_ok=True)
    sel_path = os.path.join(out_dir, f"{user_id}_feature_selector.json")
    with open(sel_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"  ✓ Feature selector → {sel_path}")
    return selector

# ── Full Per-User Pipeline ────────────────────────────────────────────────────
def train_per_user(user_id: str, out_dir: str = "checkpoints/users"):
    """Train all per-user components: autoencoder + feature selector."""
    print(f"\n{'='*60}")
    print(f"  Per-User Training: {user_id}")
    print(f"{'='*60}")

    ae_model, baseline, threshold = train_per_user_autoencoder(
        user_id=user_id, n_normal_samples=300, epochs=50, out_dir=out_dir
    )
    selector = train_per_user_feature_selector(
        user_id=user_id, n_samples=400, epochs=80, out_dir=out_dir
    )

    # Save combined profile metadata
    meta = {
        "user_id":   user_id,
        "baseline":  baseline,
        "threshold": threshold,
        "selected_features": selector.selected_names,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    meta_path = os.path.join(out_dir, f"{user_id}_profile.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\n  ✓ Profile metadata → {meta_path}")
    return meta

# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Entropy Prime — Training CLI")
    p.add_argument("--mode",         choices=["dqn", "cnn", "per_user", "all"], default="dqn")
    p.add_argument("--episodes",     type=int,   default=100_000)
    p.add_argument("--bot-ratio",    type=float, default=0.30)
    p.add_argument("--out",          type=str,   default="checkpoints/governor.pt")
    p.add_argument("--user-id",      type=str,   default="usr_example")
    p.add_argument("--n-users",      type=int,   default=20)
    p.add_argument("--out-dir",      type=str,   default="checkpoints/users")
    p.add_argument("--cnn-out",      type=str,   default="checkpoints/cnn1d_shared.pt")
    args = p.parse_args()

    if args.mode in ("dqn", "all"):
        train_dqn(args.episodes, args.bot_ratio, args.out)

    if args.mode in ("cnn", "all"):
        train_shared_cnn(n_users=args.n_users, out=args.cnn_out)

    if args.mode in ("per_user", "all"):
        if args.mode == "all":
            # Train for a batch of synthetic users
            for i in range(min(args.n_users, 5)):
                train_per_user(f"usr_{i:04d}", args.out_dir)
        else:
            train_per_user(args.user_id, args.out_dir)

    print(f"\n✓ Training complete.")
