"""
HTTP exception hierarchy.
Each exception maps directly to an HTTP status code.
"""


from .HTTPException import HTTPException
from .BadRequestException import BadRequestException
from .InternalServerError import InternalServerError
from .MethodNotAllowedException import MethodNotAllowedException
from .NotFoundException import NotFoundException


__all__ = [
    "HTTPException",
    "BadRequestException",
    "InternalServerError",
    "MethodNotAllowedException",
    "NotFoundException",
]
