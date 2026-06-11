from asyncweb.exceptions.http_exception import HTTPException


class BadRequestException(HTTPException):
    status_code = 400
    default_detail = "Bad Request"
