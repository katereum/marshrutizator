"""Доменные ошибки конвейера с понятными сообщениями (раздел 12 ТЗ)."""


class MarshrutizatorError(Exception):
    code = "ERROR"

    def __init__(self, message: str, details=None):
        super().__init__(message)
        self.message = message
        self.details = details


class FileError(MarshrutizatorError):
    code = "FILE_ERROR"


class ValidationError(MarshrutizatorError):
    code = "VALIDATION_ERROR"


class OptimizationError(MarshrutizatorError):
    code = "OPTIMIZATION_ERROR"
