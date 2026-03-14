#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import hashlib
import json
import logging
import uuid
from argparse import ArgumentParser
from http.server import BaseHTTPRequestHandler, HTTPServer

import scoring

SALT = "Otus"
ADMIN_LOGIN = "admin"
ADMIN_SALT = "42"
OK = 200
BAD_REQUEST = 400
FORBIDDEN = 403
NOT_FOUND = 404
INVALID_REQUEST = 422
INTERNAL_ERROR = 500
ERRORS = {
    BAD_REQUEST: "Bad Request",
    FORBIDDEN: "Forbidden",
    NOT_FOUND: "Not Found",
    INVALID_REQUEST: "Invalid Request",
    INTERNAL_ERROR: "Internal Server Error",
}
UNKNOWN = 0
MALE = 1
FEMALE = 2
GENDERS = {
    UNKNOWN: "unknown",
    MALE: "male",
    FEMALE: "female",
}


class Field:
    """Base descriptor for all request fields"""

    def __init__(self, required=False, nullable=False):
        self.required = required
        self.nullable = nullable
        self.name = None  # set by metaclass

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return obj.__dict__.get(self.name)

    def __set__(self, obj, value):
        obj.__dict__[self.name] = self.validate(value)

    def validate(self, value):
        """Override in subclasses"""
        return value


class CharField(Field):
    def validate(self, value):
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{self.name}: must be a string")
        return value


class ArgumentsField(Field):
    def validate(self, value):
        if value is not None and not isinstance(value, dict):
            raise ValueError(f"{self.name}: must be a dict (JSON object)")
        return value


class EmailField(CharField):
    def validate(self, value):
        value = super().validate(value)
        if value and "@" not in value:
            raise ValueError(f"{self.name}: must contain '@'")
        return value


class PhoneField(Field):
    def validate(self, value):
        if value is None:
            return value
        if not isinstance(value, (str, int)):
            raise ValueError(f"{self.name}: must be a string or integer")
        phone = str(value)
        if len(phone) != 11:
            raise ValueError(f"{self.name}: must be 11 characters long")
        if not phone.startswith("7"):
            raise ValueError(f"{self.name}: must start with '7'")
        return value


class DateField(Field):
    DATE_FORMAT = "%d.%m.%Y"

    def validate(self, value):
        if value is None or value == "":
            return value
        if not isinstance(value, str):
            raise ValueError(f"{self.name}: must be a string")
        try:
            datetime.datetime.strptime(value, self.DATE_FORMAT)
        except ValueError:
            raise ValueError(f"{self.name}: must be in DD.MM.YYYY format")
        return value

    @staticmethod
    def parse(value):
        return datetime.datetime.strptime(value, DateField.DATE_FORMAT)


class BirthDayField(DateField):
    MAX_YEARS = 70

    def validate(self, value):
        value = super().validate(value)
        if value:
            dt = self.parse(value)
            if (datetime.datetime.today() - dt).days / 365.25 > self.MAX_YEARS:
                raise ValueError(
                    f"{self.name}: birthday can't be more than {self.MAX_YEARS} years ago"
                )
        return value


class GenderField(Field):
    def validate(self, value):
        if value is None:
            return value
        if not isinstance(value, int):
            raise ValueError(f"{self.name}: must be an integer")
        if value not in GENDERS:
            raise ValueError(f"{self.name}: must be one of {list(GENDERS.keys())}")
        return value


class ClientIDsField(Field):
    def validate(self, value):
        if value is None:
            return value
        if not isinstance(value, list):
            raise ValueError(f"{self.name}: must be a list")
        if not value:
            raise ValueError(f"{self.name}: must not be empty")
        if not all(isinstance(i, int) for i in value):
            raise ValueError(f"{self.name}: all elements must be integers")
        return value


class RequestMeta(type):
    """Collects all Field instances declared in a class into `_fields`"""

    def __new__(mcs, name, bases, namespace):
        fields = {}
        for base in bases:
            if hasattr(base, "_fields"):
                fields.update(base._fields)
        for attr, value in namespace.items():
            if isinstance(value, Field):
                fields[attr] = value
        namespace["_fields"] = fields
        return super().__new__(mcs, name, bases, namespace)


class Request(metaclass=RequestMeta):
    """Base class for all API request objects"""

    def __init__(self, data: dict):
        self._errors: list[str] = []
        for name, field in self._fields.items():
            value = data.get(name)
            try:
                setattr(self, name, value)
            except ValueError as e:
                self._errors.append(str(e))

    def validate(self):
        """Check required/nullable constraints and return list of error strings"""
        errors = list(self._errors)
        for name, field in self._fields.items():
            value = getattr(self, name)
            if field.required and value is None:
                errors.append(f"{name}: required field is missing")
            elif not field.nullable and value is not None and value == "":
                errors.append(f"{name}: field must not be empty")
            elif not field.nullable and value == [] or value == {}:
                # empty collections are also not nullable
                pass
        return errors


class ClientsInterestsRequest(Request):
    client_ids = ClientIDsField(required=True)
    date = DateField(required=False, nullable=True)


class OnlineScoreRequest(Request):
    first_name = CharField(required=False, nullable=True)
    last_name = CharField(required=False, nullable=True)
    email = EmailField(required=False, nullable=True)
    phone = PhoneField(required=False, nullable=True)
    birthday = BirthDayField(required=False, nullable=True)
    gender = GenderField(required=False, nullable=True)

    VALID_PAIRS = [
        ("phone", "email"),
        ("first_name", "last_name"),
        ("gender", "birthday"),
    ]

    def validate(self):
        errors = super().validate()
        if errors:
            return errors
        has_valid_pair = any(
            getattr(self, a) is not None
            and getattr(self, b) is not None
            and getattr(self, a) != ""
            and getattr(self, b) != ""
            for a, b in self.VALID_PAIRS
        )

        def _non_empty(val):
            return val is not None and val != ""

        has_valid_pair = any(
            _non_empty(getattr(self, a)) and _non_empty(getattr(self, b))
            for a, b in self.VALID_PAIRS
        )
        if not has_valid_pair:
            errors.append(
                "At least one non-empty pair required: "
                + ", ".join(f"{a}-{b}" for a, b in self.VALID_PAIRS)
            )
        return errors


class MethodRequest(Request):
    account = CharField(required=False, nullable=True)
    login = CharField(required=True, nullable=True)
    token = CharField(required=True, nullable=True)
    arguments = ArgumentsField(required=True, nullable=True)
    method = CharField(required=True, nullable=False)

    @property
    def is_admin(self):
        return self.login == ADMIN_LOGIN


def check_auth(request: MethodRequest) -> bool:
    if request.is_admin:
        digest = hashlib.sha512(
            (datetime.datetime.now().strftime("%Y%m%d%H") + ADMIN_SALT).encode("utf-8")
        ).hexdigest()
    else:
        digest = hashlib.sha512(
            (request.account + request.login + SALT).encode("utf-8")
        ).hexdigest()
    return digest == request.token


def online_score_handler(request: MethodRequest, ctx: dict, store):
    score_req = OnlineScoreRequest(request.arguments or {})
    errors = score_req.validate()
    if errors:
        return ", ".join(errors), INVALID_REQUEST

    ctx["has"] = [
        name
        for name in score_req._fields
        if getattr(score_req, name) is not None and getattr(score_req, name) != ""
    ]

    if request.is_admin:
        return {"score": 42}, OK

    score = scoring.get_score(
        store,
        phone=score_req.phone,
        email=score_req.email,
        birthday=score_req.birthday,
        gender=score_req.gender,
        first_name=score_req.first_name,
        last_name=score_req.last_name,
    )
    return {"score": score}, OK


def clients_interests_handler(request: MethodRequest, ctx: dict, store):
    interests_req = ClientsInterestsRequest(request.arguments or {})
    errors = interests_req.validate()
    if errors:
        return ", ".join(errors), INVALID_REQUEST

    client_ids = interests_req.client_ids
    ctx["nclients"] = len(client_ids)

    response = {str(cid): scoring.get_interests(store, cid) for cid in client_ids}
    return response, OK


def method_handler(request: dict, ctx: dict, store):
    body = request.get("body", {})

    method_req = MethodRequest(body)
    errors = method_req.validate()
    if errors:
        return ", ".join(errors), INVALID_REQUEST

    if not check_auth(method_req):
        return ERRORS[FORBIDDEN], FORBIDDEN

    handlers = {
        "online_score": online_score_handler,
        "clients_interests": clients_interests_handler,
    }
    handler = handlers.get(method_req.method)
    if handler is None:
        return f"Unknown method: {method_req.method}", NOT_FOUND

    return handler(method_req, ctx, store)


class MainHTTPHandler(BaseHTTPRequestHandler):
    router = {
        "method": method_handler,
    }
    store = None

    def get_request_id(self, headers):
        return headers.get("HTTP_X_REQUEST_ID", uuid.uuid4().hex)

    def do_POST(self):
        response, code = {}, OK
        context = {"request_id": self.get_request_id(self.headers)}
        request = None
        try:
            data_string = self.rfile.read(int(self.headers["Content-Length"]))
            request = json.loads(data_string)
        except Exception:
            code = BAD_REQUEST

        if request:
            path = self.path.strip("/")
            logging.info("%s: %s %s" % (self.path, data_string, context["request_id"]))
            if path in self.router:
                try:
                    response, code = self.router[path](
                        {"body": request, "headers": self.headers}, context, self.store
                    )
                except Exception as e:
                    logging.exception("Unexpected error: %s" % e)
                    code = INTERNAL_ERROR
            else:
                code = NOT_FOUND

        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if code not in ERRORS:
            r = {"response": response, "code": code}
        else:
            r = {"error": response or ERRORS.get(code, "Unknown Error"), "code": code}
        context.update(r)
        logging.info(context)
        self.wfile.write(json.dumps(r).encode("utf-8"))

    def log_message(self, format, *args):
        # Suppress default HTTPServer logging
        pass


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-p", "--port", action="store", type=int, default=8080)
    parser.add_argument("-l", "--log", action="store", default=None)
    args = parser.parse_args()
    logging.basicConfig(
        filename=args.log,
        level=logging.INFO,
        format="[%(asctime)s] %(levelname).1s %(message)s",
        datefmt="%Y.%m.%d %H:%M:%S",
    )
    server = HTTPServer(("", args.port), MainHTTPHandler)
    logging.info("Starting server at %s" % args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
