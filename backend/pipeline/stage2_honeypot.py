"""pipeline/stage2_honeypot.py — redirect to models.stage2_honeypot."""
try:
    from ..models.stage2_honeypot import (  # noqa: F401
        ChallengeConfig,
        DecoySpec,
        run,
        update_mab_reward,
        verify_challenge_signature,
    )
except ImportError:
    from models.stage2_honeypot import (  # type: ignore # noqa: F401
        ChallengeConfig,
        DecoySpec,
        run,
        update_mab_reward,
        verify_challenge_signature,
    )
