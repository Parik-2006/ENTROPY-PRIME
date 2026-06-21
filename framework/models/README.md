# framework/models — Model Registry & Checkpoints

Logical home for the framework's ML model registry, checkpoint provenance, and
offline training entry points. At the facade stage the model *code* still lives
under `backend/models/` and is re-exported by each engine; this folder
documents the registry and will host the relocated training scripts.

## Model registry (canonical source today)

| Model | Source file | Engine | In -> Out | Checkpoint env |
|---|---|---|---|---|
| CNN1D (server embed) | `backend/models/cnn1d.py` | cadence | raw signal -> 32-dim | `EP_CNN_CHECKPOINT` |
| 1D-CNN (browser theta) | `src/services/biometrics.js` | cadence | [50x8] -> theta | (tfjs, in-browser) |
| Autoencoder | `src/services/biometrics.js` | continuous_auth | [400] -> latent[32], e_rec | (tfjs, in-browser) |
| MABAgent (UCB1) | `backend/models/mab.py` | honeypot | reward -> arm 0/1/2 | `EP_MAB_CHECKPOINT` (`checkpoints/mab.json`) |
| DQNAgent | `backend/models/dqn.py` | dms | [theta,load,suspect] -> preset 0-3 | `EP_RL_CHECKPOINT` (`governor.pt`) |
| PPOPolicyAgent | `backend/models/ppo_agents.py` | dms | [theta,load,suspect,bot,risk] -> action | `EP_GOV_PPO_CHECKPOINT` |
| PPOAgent (actor-critic) | `backend/models/ppo.py` | continuous_auth | 10-dim -> (action, prob) | `EP_PPO_CHECKPOINT` (`watchdog.pt`) |

## Checkpoint provenance note
Only `checkpoints/mab.json` is committed; the `.pt` weights are git-ignored
(`.gitignore`). With no `.pt` present, DQN/PPO/CNN run with **random weights**
and the system relies on the deterministic hard-override rules in
`stage3_governor.py` and the threshold fallback in `stage4_watchdog.py`.
Training entry points: `backend/train.py`, `backend/models/train_*.py`.

## CRITICAL invariant to preserve during migration
- Stage 3 governor MUST use `PPOPolicyAgent` (`select_action -> int`).
- Stage 4 watchdog MUST use `PPOAgent` (`select_action -> (int, float)`).
Swapping them reintroduces the historical "BUG-A" `TypeError`
(see `backend/main.py` header, lines 15-29).
