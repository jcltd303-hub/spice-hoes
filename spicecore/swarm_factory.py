"""Construct the production swarm using device-local planning and S24 workers."""

import os
import shutil
from pathlib import Path

from .assetgen import AssetGenerator
from .autopilot import CoreAutopilot
from .local_compute import chat_provider
from .experiments import ExperimentPlanner
from .learning import LearningController
from .memory import KnowledgeBase
from .moa import MixtureOfAgents
from .runtime_policy import RuntimePolicy
from .providers import GoMediaProvider
from .swarm import SwarmConfig, SwarmRuntime


def production_blockers(config):
    missing = []
    try:
        provider = chat_provider()
        if hasattr(provider, "readiness") and not provider.readiness()["ready"]:
            missing.append("local_chat_unavailable")
    except (ValueError, RuntimeError):
        missing.append("valid_local_model_configuration")
    token_env = {"instagram": "INSTAGRAM_ACCESS_TOKEN", "tiktok": "TIKTOK_ACCESS_TOKEN",
                 "youtube_shorts": "YOUTUBE_ACCESS_TOKEN"}[config.channel]
    if not os.getenv(token_env):
        missing.append(token_env)
    binary = os.getenv("SPICE_MEDIA_BIN", "bin/spicemedia")
    if not (Path(binary).is_file() and os.access(binary, os.X_OK)) and not shutil.which(binary):
        missing.append("SPICE_MEDIA_BIN")
    if not os.getenv("SPICE_QNN_MODEL_DIR") or not Path(os.getenv("SPICE_QNN_MODEL_DIR", "")).is_dir():
        missing.append("SPICE_QNN_MODEL_DIR")
    if config.channel in ("instagram", "tiktok"):
        if not os.getenv("SPICE_MEDIA_PUBLIC_BASE_URL"):
            missing.append("SPICE_MEDIA_PUBLIC_BASE_URL")
        else:
            from .media_delivery import MediaDelivery
            try:
                if not MediaDelivery.from_env().readiness()["ready"]:
                    missing.append("public_media_directory_unavailable")
            except ValueError:
                missing.append("valid_public_media_configuration")
    if not os.getenv("STRIPE_WEBHOOK_SECRET"):
        missing.append("STRIPE_WEBHOOK_SECRET")
    return missing


def make_swarm(store, personas, config: SwarmConfig):
    from .commerce import StripeCommerce
    from .distribution.instagram import InstagramGraphPublisher
    from .distribution.tiktok import TikTokPublisher
    from .distribution.youtube import YouTubeShortsPublisher
    from .media_delivery import MediaDelivery

    publishers = {"instagram": InstagramGraphPublisher(), "tiktok": TikTokPublisher(),
                  "youtube_shorts": YouTubeShortsPublisher()}
    media_delivery = None
    try:
        media_delivery = MediaDelivery.from_env()
    except ValueError:
        pass
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    commerce = StripeCommerce(store, secret) if secret else None
    autopilot = learning = None
    if not production_blockers(config):
        provider = chat_provider()
        values = RuntimePolicy(store).current()["values"]
        planner = ExperimentPlanner(provider, store)
        knowledge = KnowledgeBase(store)
        moa = MixtureOfAgents(provider, store)
        generator = AssetGenerator(
            store, GoMediaProvider(),
            identity_threshold=values["identity_threshold"],
            quality_threshold=values["quality_threshold"],
            reference_strength=values["reference_strength"])
        autopilot = CoreAutopilot(store, personas, moa, planner, generator,
                                  min_experiences=values["rl_min_experiences"],
                                  verified_revenue_only=True)
        learning = LearningController(store, personas, planner, knowledge,
                                       min_experiences=values["rl_min_experiences"],
                                       verified_revenue_only=True)
    else:
        # Learning and delivery of earlier approved batches do not require model compute.
        planner = ExperimentPlanner(None, store)
        learning = LearningController(store, personas, planner, KnowledgeBase(store),
                                       min_experiences=RuntimePolicy(store).current()["values"]["rl_min_experiences"],
                                       verified_revenue_only=True)
    return SwarmRuntime(store, personas, config, autopilot=autopilot, learning=learning,
                        publishers=publishers, media_delivery=media_delivery, commerce=commerce,
                        production_blockers=lambda: production_blockers(config))
