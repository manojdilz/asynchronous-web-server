from asyncweb.exceptions.HTTPException import HTTPException


class NotFoundException(HTTPException):
    status_code = 404
    default_detail = "Not Found"
