"""Isolated integrations for authorized singing-synthesis providers."""

from services.audio.providers.diffsinger import DiffSingerCliProvider, SingingConfigurationError, SingingProviderError

__all__ = ["DiffSingerCliProvider", "SingingConfigurationError", "SingingProviderError"]
