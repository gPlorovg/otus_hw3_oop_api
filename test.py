import datetime
import functools
import hashlib
import json
import unittest

import api
import scoring


def cases(cases_list):
    """Parametrize a test method with multiple input cases.

    On failure each subtest reports exactly which case caused it.
    """

    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args):
            for c in cases_list:
                with args[0].subTest(case=c):
                    new_args = args + (c if isinstance(c, tuple) else (c,))
                    f(*new_args)

        return wrapper

    return decorator


class FakeStore:
    """In-memory store that implements the same interface as RedisStore.

    Pass ``unavailable=True`` to simulate a broken connection:
    - ``get`` raises ``ConnectionError``
    - ``cache_get`` / ``cache_set`` silently do nothing
    """

    def __init__(self, data: dict | None = None, unavailable: bool = False):
        self._data: dict = dict(data or {})
        self._unavailable = unavailable

    def get(self, key: str):
        if self._unavailable:
            raise ConnectionError("Store unavailable")
        return self._data.get(key)

    def cache_get(self, key: str):
        if self._unavailable:
            return None
        return self._data.get(key)

    def cache_set(self, key: str, value, ttl=None):
        if not self._unavailable:
            self._data[key] = str(value)


def _make_interests_store(*cids) -> FakeStore:
    """Return a FakeStore pre-populated with two interests for each given cid"""
    data = {f"i:{cid}": json.dumps(["books", "hi-tech"]) for cid in cids}
    return FakeStore(data=data)


class TestSuite(unittest.TestCase):
    def setUp(self):
        self.context = {}
        self.headers = {}
        self.store = _make_interests_store(*range(10))

    def get_response(self, request):
        return api.method_handler(
            {"body": request, "headers": self.headers}, self.context, self.store
        )

    def set_valid_auth(self, request):
        if request.get("login") == api.ADMIN_LOGIN:
            request["token"] = hashlib.sha512(
                (datetime.datetime.now().strftime("%Y%m%d%H") + api.ADMIN_SALT).encode(
                    "utf-8"
                )
            ).hexdigest()
        else:
            msg = (
                request.get("account", "") + request.get("login", "") + api.SALT
            ).encode("utf-8")
            request["token"] = hashlib.sha512(msg).hexdigest()

    def test_empty_request(self):
        _, code = self.get_response({})
        self.assertEqual(api.INVALID_REQUEST, code)

    @cases(
        [
            {
                "account": "horns&hoofs",
                "login": "h&f",
                "method": "online_score",
                "token": "",
                "arguments": {},
            },
            {
                "account": "horns&hoofs",
                "login": "h&f",
                "method": "online_score",
                "token": "sdd",
                "arguments": {},
            },
            {
                "account": "horns&hoofs",
                "login": "admin",
                "method": "online_score",
                "token": "",
                "arguments": {},
            },
        ]
    )
    def test_bad_auth(self, request):
        _, code = self.get_response(request)
        self.assertEqual(api.FORBIDDEN, code)

    @cases(
        [
            {"account": "horns&hoofs", "login": "h&f", "method": "online_score"},
            {"account": "horns&hoofs", "login": "h&f", "arguments": {}},
            {"account": "horns&hoofs", "method": "online_score", "arguments": {}},
        ]
    )
    def test_invalid_method_request(self, request):
        self.set_valid_auth(request)
        response, code = self.get_response(request)
        self.assertEqual(api.INVALID_REQUEST, code)
        self.assertTrue(len(response))

    @cases(
        [
            {},
            {"phone": "79175002040"},
            {"phone": "89175002040", "email": "stupnikov@otus.ru"},
            {"phone": "79175002040", "email": "stupnikovotus.ru"},
            {"phone": "79175002040", "email": "stupnikov@otus.ru", "gender": -1},
            {"phone": "79175002040", "email": "stupnikov@otus.ru", "gender": "1"},
            {
                "phone": "79175002040",
                "email": "stupnikov@otus.ru",
                "gender": 1,
                "birthday": "01.01.1890",
            },
            {
                "phone": "79175002040",
                "email": "stupnikov@otus.ru",
                "gender": 1,
                "birthday": "XXX",
            },
            {
                "phone": "79175002040",
                "email": "stupnikov@otus.ru",
                "gender": 1,
                "birthday": "01.01.2000",
                "first_name": 1,
            },
            {
                "phone": "79175002040",
                "email": "stupnikov@otus.ru",
                "gender": 1,
                "birthday": "01.01.2000",
                "first_name": "s",
                "last_name": 2,
            },
            {"phone": "79175002040", "birthday": "01.01.2000", "first_name": "s"},
            {"email": "stupnikov@otus.ru", "gender": 1, "last_name": 2},
        ]
    )
    def test_invalid_score_request(self, arguments):
        request = {
            "account": "horns&hoofs",
            "login": "h&f",
            "method": "online_score",
            "arguments": arguments,
        }
        self.set_valid_auth(request)
        response, code = self.get_response(request)
        self.assertEqual(api.INVALID_REQUEST, code, arguments)
        self.assertTrue(len(response))

    @cases(
        [
            {"phone": "79175002040", "email": "stupnikov@otus.ru"},
            {"phone": 79175002040, "email": "stupnikov@otus.ru"},
            {
                "gender": 1,
                "birthday": "01.01.2000",
                "first_name": "a",
                "last_name": "b",
            },
            {"gender": 0, "birthday": "01.01.2000"},
            {"gender": 2, "birthday": "01.01.2000"},
            {"first_name": "a", "last_name": "b"},
            {
                "phone": "79175002040",
                "email": "stupnikov@otus.ru",
                "gender": 1,
                "birthday": "01.01.2000",
                "first_name": "a",
                "last_name": "b",
            },
        ]
    )
    def test_ok_score_request(self, arguments):
        request = {
            "account": "horns&hoofs",
            "login": "h&f",
            "method": "online_score",
            "arguments": arguments,
        }
        self.set_valid_auth(request)
        response, code = self.get_response(request)
        self.assertEqual(api.OK, code, arguments)
        score = response.get("score")
        self.assertTrue(isinstance(score, (int, float)) and score >= 0, arguments)
        self.assertEqual(sorted(self.context["has"]), sorted(arguments.keys()))

    def test_ok_score_admin_request(self):
        arguments = {"phone": "79175002040", "email": "stupnikov@otus.ru"}
        request = {
            "account": "horns&hoofs",
            "login": "admin",
            "method": "online_score",
            "arguments": arguments,
        }
        self.set_valid_auth(request)
        response, code = self.get_response(request)
        self.assertEqual(api.OK, code)
        score = response.get("score")
        self.assertEqual(score, 42)

    @cases(
        [
            {},
            {"date": "20.07.2017"},
            {"client_ids": [], "date": "20.07.2017"},
            {"client_ids": {1: 2}, "date": "20.07.2017"},
            {"client_ids": ["1", "2"], "date": "20.07.2017"},
            {"client_ids": [1, 2], "date": "XXX"},
        ]
    )
    def test_invalid_interests_request(self, arguments):
        request = {
            "account": "horns&hoofs",
            "login": "h&f",
            "method": "clients_interests",
            "arguments": arguments,
        }
        self.set_valid_auth(request)
        response, code = self.get_response(request)
        self.assertEqual(api.INVALID_REQUEST, code, arguments)
        self.assertTrue(len(response))

    @cases(
        [
            {
                "client_ids": [1, 2, 3],
                "date": datetime.datetime.today().strftime("%d.%m.%Y"),
            },
            {"client_ids": [1, 2], "date": "19.07.2017"},
            {"client_ids": [0]},
        ]
    )
    def test_ok_interests_request(self, arguments):
        request = {
            "account": "horns&hoofs",
            "login": "h&f",
            "method": "clients_interests",
            "arguments": arguments,
        }
        self.set_valid_auth(request)
        response, code = self.get_response(request)
        self.assertEqual(api.OK, code, arguments)
        self.assertEqual(len(arguments["client_ids"]), len(response))
        self.assertTrue(
            all(
                v
                and isinstance(v, list)
                and all(isinstance(i, (bytes, str)) for i in v)
                for v in response.values()
            )
        )
        self.assertEqual(self.context.get("nclients"), len(arguments["client_ids"]))


class TestFieldValidation(unittest.TestCase):
    """Unit tests for individual Field descriptor validators"""

    def _field(self, cls, **kwargs):
        f = cls(**kwargs)
        f.name = "f"
        return f

    def test_char_field_accepts_string(self):
        f = self._field(api.CharField)
        self.assertEqual("hello", f.validate("hello"))

    def test_char_field_accepts_none(self):
        f = self._field(api.CharField)
        self.assertIsNone(f.validate(None))

    def test_char_field_rejects_non_string(self):
        f = self._field(api.CharField)
        with self.assertRaises(ValueError):
            f.validate(42)

    def test_email_field_requires_at_sign(self):
        f = self._field(api.EmailField)
        with self.assertRaises(ValueError):
            f.validate("noatsign.com")

    def test_email_field_accepts_valid_email(self):
        f = self._field(api.EmailField)
        self.assertEqual("a@b.com", f.validate("a@b.com"))

    def test_email_field_accepts_empty(self):
        f = self._field(api.EmailField)
        self.assertEqual("", f.validate(""))

    @cases(
        [
            "1234567890",  # 10 chars
            "791750020401",  # 12 chars
            "89175002040",  # starts with 8
            "7917500204x",  # non-digit (length ok, starts with 7)
        ]
    )
    def test_phone_field_rejects_invalid(self, value):
        f = self._field(api.PhoneField)
        with self.assertRaises(ValueError):
            f.validate(value)

    def test_phone_field_accepts_string(self):
        f = self._field(api.PhoneField)
        self.assertEqual("79175002040", f.validate("79175002040"))

    def test_phone_field_accepts_int(self):
        f = self._field(api.PhoneField)
        self.assertEqual(79175002040, f.validate(79175002040))

    def test_date_field_accepts_valid_date(self):
        f = self._field(api.DateField)
        self.assertEqual("01.01.2000", f.validate("01.01.2000"))

    def test_date_field_rejects_wrong_format(self):
        f = self._field(api.DateField)
        with self.assertRaises(ValueError):
            f.validate("2000-01-01")

    def test_date_field_rejects_garbage(self):
        f = self._field(api.DateField)
        with self.assertRaises(ValueError):
            f.validate("XXX")

    def test_birthday_field_rejects_too_old(self):
        f = self._field(api.BirthDayField)
        with self.assertRaises(ValueError):
            f.validate("01.01.1890")

    def test_birthday_field_accepts_recent(self):
        f = self._field(api.BirthDayField)
        self.assertEqual("01.01.2000", f.validate("01.01.2000"))

    @cases([api.UNKNOWN, api.MALE, api.FEMALE])
    def test_gender_field_accepts_valid(self, value):
        f = self._field(api.GenderField)
        self.assertEqual(value, f.validate(value))

    @cases([-1, 3, "1"])
    def test_gender_field_rejects_invalid(self, value):
        f = self._field(api.GenderField)
        with self.assertRaises(ValueError):
            f.validate(value)

    def test_client_ids_rejects_empty_list(self):
        f = self._field(api.ClientIDsField)
        with self.assertRaises(ValueError):
            f.validate([])

    def test_client_ids_rejects_non_int_elements(self):
        f = self._field(api.ClientIDsField)
        with self.assertRaises(ValueError):
            f.validate(["1", "2"])

    def test_client_ids_rejects_dict(self):
        f = self._field(api.ClientIDsField)
        with self.assertRaises(ValueError):
            f.validate({1: 2})

    def test_client_ids_accepts_valid_list(self):
        f = self._field(api.ClientIDsField)
        self.assertEqual([1, 2, 3], f.validate([1, 2, 3]))


class TestGetScore(unittest.TestCase):
    """Unit tests for scoring.get_score with FakeStore"""

    def test_returns_float(self):
        store = FakeStore()
        result = scoring.get_score(store, phone="79175002040", email="x@y.com")
        self.assertIsInstance(result, float)

    def test_phone_email_pair_gives_3_points(self):
        store = FakeStore()
        score = scoring.get_score(store, phone="79175002040", email="x@y.com")
        self.assertEqual(3.0, score)

    def test_first_last_name_gives_half_point(self):
        store = FakeStore()
        score = scoring.get_score(store, first_name="Ivan", last_name="Petrov")
        self.assertEqual(0.5, score)

    def test_gender_birthday_gives_1_5_points(self):
        store = FakeStore()
        bd = datetime.datetime(2000, 1, 1)
        score = scoring.get_score(store, gender=api.MALE, birthday=bd)
        self.assertEqual(1.5, score)

    def test_cache_hit_returns_cached_value(self):
        store = FakeStore()
        key = list(store._data.keys())[0]
        store._data[key] = "99.9"
        score2 = scoring.get_score(store, phone="79175002040", email="x@y.com")
        self.assertEqual(99.9, score2)

    def test_works_when_store_unavailable(self):
        """get_score must not raise when the cache store is down"""
        store = FakeStore(unavailable=True)
        score = scoring.get_score(store, phone="79175002040", email="x@y.com")
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0)

    def test_empty_args_give_zero_score(self):
        store = FakeStore()
        score = scoring.get_score(store)
        self.assertEqual(0.0, score)


class TestGetInterests(unittest.TestCase):
    """Unit tests for scoring.get_interests with FakeStore"""

    def test_returns_list_from_store(self):
        store = FakeStore(data={"i:1": json.dumps(["books", "cars"])})
        result = scoring.get_interests(store, 1)
        self.assertEqual(["books", "cars"], result)

    def test_returns_empty_list_when_key_missing(self):
        store = FakeStore()
        result = scoring.get_interests(store, 999)
        self.assertEqual([], result)

    def test_raises_when_store_unavailable(self):
        """get_interests must propagate store errors (persistent storage)"""
        store = FakeStore(unavailable=True)
        with self.assertRaises(Exception):
            scoring.get_interests(store, 1)


if __name__ == "__main__":
    unittest.main()
