"""
Entropy Prime — CNN1D Training Scripts

Provides:
  1. train_shared()        — train shared backbone on multi-user synthetic data
  2. finetune_per_user()   — fine-tune per-user adapter on user's behavioral data
  3. evaluate_per_user()   — evaluate reconstruction error + drift detection

Usage:
    cd backend/models
    python train_cnn1d.py --mode shared
    python train_cnn1d.py --mode finetune --user-id usr_abc123
    python train_cnn1d.py --mode evaluate --user-id usr_abc123
    python train_cnn1d.py --mode all --n-users 10
"""
import argparse, os, sys, time, json
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

# Allow imports from parent dir
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.cnn1d import CNN1D, PerUserCNN1D, FeatureSelector, FullPerUserPipeline

# ── Constants ─────────────────────────────────────────────────────────────────
N_FEATURES = 8
SEQ_LEN    = 50
LATENT_DIM = 32
FEATURE_NAMES = [
    "dwell_norm", "flight_norm", "speed_norm", "jitter_norm",
    "accel_norm",  "rhythm_norm", "pause_norm",  "bigram_norm",
]

# ── Per-User Behavior Simulator ───────────────────────────────────────────────
class UserSimulator:
    """Generates synthetic per-user behavioral sequences."""
    def __init__(self, user_id: str, seed: int = None):
        rng = np.random.RandomState(seed if seed is not None else abs(hash(user_id)) % 2**31)
        self.user_id  = user_id
        # Each user has stable mean + individual noise level per feature
        self.means    = rng.beta(4, 2, size=N_FEATURES).astype(np.float32)
        self.stds     = rng.beta(2, 8, size=N_FEATURES).astype(np.float32) * 0.15
        # Some users are highly consistent, others vary more
        self.consistency = float(rng.beta(5, 2))

    def sample_sequences(self, n: int, drifted: bool = False) -> torch.Tensor:
        """Return [n, N_FEATURES, SEQ_LEN] tensor."""
        sequences = np.zeros((n, SEQ_LEN, N_FEATURES), dtype=np.float32)
        for i in range(n):
            if drifted:
                # Shift means by random amount across features
                shift  = np.random.randn(N_FEATURES).astype(np.float32) * self.stds * 5
                means_ = np.clip(self.means + shift, 0, 1)
                stds_  = self.stds * 2
            else:
                means_ = self.means
                stds_  = self.stds
            noise = np.random.randn(SEQ_LEN, N_FEATURES).astype(np.float32)
            sequences[i] = np.clip(means_[None, :] + stds_[None, :] * noise, 0, 1)
        # [n, SEQ_LEN, N_FEATURES] → [n, N_FEATURES, SEQ_LEN]
        return torch.FloatTensor(sequences.transpose(0, 2, 1))

    def sample_flat(self, n: int, drifted: bool = False) -> np.ndarray:
        """Return [n, N_FEATURES] flat vectors."""
        if drifted:
            shift  = np.random.randn(N_FEATURES).astype(np.float32) * self.stds * 4
            means_ = np.clip(self.means + shift, 0, 1)
        else:
            means_ = self.means
        noise = np.random.randn(n, N_FEATURES).astype(np.float32)
        return np.clip(means_[None, :] + self.stds[None, :] * noise, 0, 1)

# ── 1. Shared Backbone Training ───────────────────────────────────────────────
def train_shared(
    n_users: int       = 50,
    samples_per_user:  int = 200,
    bot_ratio: float   = 0.25,
    epochs: int        = 40,
    lr: float          = 1e-3,
    batch_size: int    = 64,
    out: str           = "../../checkpoints/cnn1d_shared.pt",
):
    """
    Train shared CNN1D backbone on synthetic multi-user data.
    Task: human (1) vs bot (0) binary classification using 8-channel sequences.
    """
    print(f"\n[CNN1D Shared] {n_users} users × {samples_per_user} samples, epochs={epochs}")
    print("─" * 60)

    # Build model with binary output for classification
    model = CNN1D(input_channels=N_FEATURES, out_dim=1, seq_len=SEQ_LEN)
    model.head = nn.Sequential(
        nn.Linear(64, 32), nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(32, 1), nn.Sigmoid(),
    )
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    criterion = nn.BCELoss()
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    # Build dataset
    X_list, y_list = [], []
    sims = [UserSimulator(f"usr_{i:04d}", seed=i) for i in range(n_users)]
    n_bots = max(1, int(n_users * bot_ratio))
    bot_sims = [UserSimulator(f"bot_{i:04d}", seed=n_users + i) for i in range(n_bots)]

    for sim in sims:
        X_list.append(sim.sample_sequences(samples_per_user, drifted=False))
        y_list.append(torch.ones(samples_per_user, 1))
    for sim in bot_sims:
        n_bot_samples = samples_per_user // 4
        X_list.append(sim.sample_sequences(n_bot_samples, drifted=True))
        y_list.append(torch.zeros(n_bot_samples, 1))

    X = torch.cat(X_list, dim=0)
    y = torch.cat(y_list, dim=0)
    perm = torch.randperm(len(X)); X, y = X[perm], y[perm]
    n_total = len(X)
    print(f"  Dataset: {n_total} samples ({int(y.sum())} human, {n_total - int(y.sum())} bot)")

    best_loss = float("inf")
    t0 = time.time()

    for epoch in range(1, epochs + 1):
        model.train()
        perm_e   = torch.randperm(n_total)
        X_e, y_e = X[perm_e], y[perm_e]
        epoch_loss, n_batches = 0., 0

        for i in range(0, n_total, batch_size):
            xb, yb = X_e[i:i+batch_size], y_e[i:i+batch_size]
            if len(xb) < 2: continue
            out  = model(xb)
            loss = criterion(out, yb)
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            epoch_loss += loss.item(); n_batches += 1

        scheduler.step()
        epoch_loss /= max(n_batches, 1)
        if epoch_loss < best_loss: best_loss = epoch_loss

        if epoch % 10 == 0 or epoch == epochs:
            elapsed = time.time() - t0
            print(f"  epoch {epoch:>3}/{epochs} | loss {epoch_loss:.4f} | best {best_loss:.4f} | {elapsed:.0f}s")

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    torch.save({
        "model":     model.state_dict(),
        "n_users":   n_users,
        "epochs":    epochs,
        "best_loss": best_loss,
    }, out)
    print(f"✓ Shared CNN1D → {out}")
    return model

# ── 2. Per-User Fine-Tuning ───────────────────────────────────────────────────
def finetune_per_user(
    user_id: str,
    base_checkpoint: str  = "../../checkpoints/cnn1d_shared.pt",
    n_samples: int        = 300,
    epochs: int           = 30,
    lr: float             = 5e-4,
    batch_size: int       = 32,
    out_dir: str          = "../../checkpoints/users",
):
    """
    Fine-tune per-user adapter on top of frozen shared backbone.
    Trains FullPerUserPipeline: FeatureSelector → CNN1D backbone → PerUserAdapter.
    """
    print(f"\n[CNN1D Fine-Tune] user={user_id}, samples={n_samples}, epochs={epochs}")

    # Load shared backbone
    base_model = CNN1D(input_channels=N_FEATURES, out_dim=LATENT_DIM, seq_len=SEQ_LEN)
    if os.path.exists(base_checkpoint):
        ckpt = torch.load(base_checkpoint, map_location="cpu")
        # Load only backbone weights (head shape may differ)
        state = {k: v for k, v in ckpt["model"].items() if "backbone" in k}
        base_model.load_state_dict(state, strict=False)
        print(f"  Loaded backbone from {base_checkpoint}")
    else:
        print(f"  Warning: checkpoint not found, using random init backbone")

    # Build full per-user pipeline
    pipeline  = FullPerUserPipeline(base_model, user_id)
    sim       = UserSimulator(user_id)

    # Target: encode user's normal sequences through backbone to get reference latents
    X_normal  = sim.sample_sequences(n_samples, drifted=False)
    X_drifted = sim.sample_sequences(n_samples // 5, drifted=True)
    X_all = torch.cat([X_normal, X_drifted], dim=0)
    # Contrastive labels: 1 = normal, 0 = drifted
    y_all = torch.cat([torch.ones(n_samples, 1), torch.zeros(n_samples // 5, 1)], dim=0)
    perm  = torch.randperm(len(X_all)); X_all, y_all = X_all[perm], y_all[perm]

    # Probe head for fine-tuning signal
    probe     = nn.Sequential(nn.Linear(LATENT_DIM, 16), nn.ReLU(), nn.Linear(16, 1), nn.Sigmoid())
    params    = (list(pipeline.feat_selector.parameters()) +
                 list(pipeline.user_cnn.adapter.parameters()) +
                 list(pipeline.user_cnn.user_head.parameters()) +
                 list(probe.parameters()))
    optimizer = optim.Adam(params, lr=lr)
    criterion = nn.BCELoss()
    best_loss = float("inf")

    for epoch in range(1, epochs + 1):
        pipeline.train(); probe.train()
        perm_e   = torch.randperm(len(X_all))
        X_e, y_e = X_all[perm_e], y_all[perm_e]
        epoch_loss, n_batches = 0., 0

        for i in range(0, len(X_e), batch_size):
            xb, yb = X_e[i:i+batch_size], y_e[i:i+batch_size]
            if len(xb) < 2: continue
            feats = pipeline(xb)
            out   = probe(feats)
            # BCE + L1 on feature selector logits for sparsity
            loss  = (criterion(out, yb) +
                     0.005 * pipeline.feat_selector.logits.abs().mean())
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            epoch_loss += loss.item(); n_batches += 1

        epoch_loss /= max(n_batches, 1)
        if epoch_loss < best_loss: best_loss = epoch_loss

    pipeline.eval()
    sel_state = pipeline.get_selection_state()
    print(f"  Selected: {sel_state['selected_names']}")

    os.makedirs(out_dir, exist_ok=True)
    ckpt_path = os.path.join(out_dir, f"{user_id}_pipeline.pt")
    torch.save({
        "pipeline_state":  pipeline.state_dict(),
        "user_id":         user_id,
        "selected_indices": sel_state["selected_indices"],
        "selected_names":   sel_state["selected_names"],
        "epochs":          epochs,
        "best_loss":       best_loss,
    }, ckpt_path)
    print(f"  ✓ Per-user pipeline → {ckpt_path}")
    return pipeline

# ── 3. Per-User Evaluation ────────────────────────────────────────────────────
def evaluate_per_user(
    user_id: str,
    pipeline_checkpoint: str = None,
    n_eval: int = 100,
    out_dir: str = "../../checkpoints/users",
):
    """
    Evaluate a trained per-user pipeline.
    Computes reconstruction error distribution and drift threshold.
    """
    print(f"\n[CNN1D Eval] user={user_id}")

    if pipeline_checkpoint is None:
        pipeline_checkpoint = os.path.join(out_dir, f"{user_id}_pipeline.pt")

    if not os.path.exists(pipeline_checkpoint):
        print(f"  No checkpoint found at {pipeline_checkpoint}")
        return

    ckpt     = torch.load(pipeline_checkpoint, map_location="cpu")
    sim      = UserSimulator(user_id)

    # Reconstruct pipeline (needs base model)
    base_model = CNN1D(input_channels=N_FEATURES, out_dim=LATENT_DIM, seq_len=SEQ_LEN)
    pipeline   = FullPerUserPipeline(base_model, user_id)
    pipeline.load_state_dict(ckpt["pipeline_state"], strict=False)
    pipeline.eval()

    X_normal  = sim.sample_sequences(n_eval, drifted=False)
    X_drifted = sim.sample_sequences(n_eval, drifted=True)

    with torch.no_grad():
        feats_normal  = pipeline(X_normal).numpy()
        feats_drifted = pipeline(X_drifted).numpy()

    # Compute cosine similarity to centroid
    centroid = feats_normal.mean(axis=0)
    def cosine_sim(a, b):
        a_n = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-8)
        b_n = b / (np.linalg.norm(b) + 1e-8)
        return (a_n @ b_n)

    sim_normal  = cosine_sim(feats_normal, centroid)
    sim_drifted = cosine_sim(feats_drifted, centroid)

    threshold = float(sim_normal.mean() - 2 * sim_normal.std())
    print(f"  Normal  sim: {sim_normal.mean():.3f} ± {sim_normal.std():.3f}")
    print(f"  Drifted sim: {sim_drifted.mean():.3f} ± {sim_drifted.std():.3f}")
    print(f"  Threshold:   {threshold:.3f}")
    print(f"  Selected:    {ckpt.get('selected_names', 'N/A')}")

    report = {
        "user_id":       user_id,
        "normal_mean":   float(sim_normal.mean()),
        "normal_std":    float(sim_normal.std()),
        "drifted_mean":  float(sim_drifted.mean()),
        "drifted_std":   float(sim_drifted.std()),
        "threshold":     threshold,
        "selected":      ckpt.get("selected_names", []),
        "evaluated_at":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    report_path = os.path.join(out_dir, f"{user_id}_eval.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  ✓ Eval report → {report_path}")
    return report

# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mode",     choices=["shared", "finetune", "evaluate", "all"], default="shared")
    p.add_argument("--user-id",  type=str, default="usr_example")
    p.add_argument("--n-users",  type=int, default=10)
    p.add_argument("--epochs",   type=int, default=40)
    p.add_argument("--samples",  type=int, default=300)
    p.add_argument("--out-dir",  type=str, default="../../checkpoints/users")
    p.add_argument("--cnn-out",  type=str, default="../../checkpoints/cnn1d_shared.pt")
    args = p.parse_args()

    if args.mode in ("shared", "all"):
        train_shared(n_users=args.n_users, epochs=args.epochs, out=args.cnn_out)

    if args.mode in ("finetune", "all"):
        user_ids = [f"usr_{i:04d}" for i in range(args.n_users)] if args.mode == "all" else [args.user_id]
        for uid in user_ids:
            finetune_per_user(uid, base_checkpoint=args.cnn_out,
                              n_samples=args.samples, out_dir=args.out_dir)

    if args.mode in ("evaluate", "all"):
        user_ids = [f"usr_{i:04d}" for i in range(min(args.n_users, 3))] if args.mode == "all" else [args.user_id]
        for uid in user_ids:
            evaluate_per_user(uid, out_dir=args.out_dir)

    print("\n✓ CNN1D training complete.")
