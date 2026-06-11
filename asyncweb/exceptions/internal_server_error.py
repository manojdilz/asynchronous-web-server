from asyncweb.exceptions.http_exception import HTTPException


class InternalServerError(HTTPException):
    status_code = 500
    default_detail = "Internal Server Error"
