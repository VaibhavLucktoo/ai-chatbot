"""Configuration domain errors shared by services and HTTP adapters."""


class AssistantNotFound(RuntimeError):
    pass


class AssistantAccessError(RuntimeError):
    pass


class AssistantConfigurationError(RuntimeError):
    pass


class AssistantConflict(RuntimeError):
    pass
