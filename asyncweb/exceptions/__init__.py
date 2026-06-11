"""
HTTP exception hierarchy.
Each exception maps directly to an HTTP status code.
"""


from asyncweb.exceptions.http_exception import HTTPException
from asyncweb.exceptions.bad_request_exception import BadRequestException
from asyncweb.exceptions.internal_server_error import InternalServerError
from asyncweb.exceptions.method_not_allowed_exception import MethodNotAllowedException
from asyncweb.exceptions.notfound_exception import NotFoundException


__all__ = [
    "HTTPException",
    "BadRequestException",
    "InternalServerError",
    "MethodNotAllowedException",
    "NotFoundException",
]
