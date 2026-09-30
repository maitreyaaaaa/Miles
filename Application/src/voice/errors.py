class VoiceProviderError(RuntimeError):
    """A live voice dependency failed; never substitute a simulated session."""
