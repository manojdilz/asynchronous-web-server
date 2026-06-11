from asyncweb.exceptions.HTTPException import HTTPException


class MethodNotAllowedException(HTTPException):
    status_code = 405
    default_detail = "Method Not Allowed"
