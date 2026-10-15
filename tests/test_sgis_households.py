"""SGIS tests use synthetic responses; no secrets or live endpoint needed."""
import unittest
from unittest.mock import Mock
import requests

from sgis_households import SGISError, SGISHouseholdClient, classify_site


class Response:
    def __init__(self, body=None, error=None):
        self.body, self.error = body, error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.body


def ok(result):
    return Response({"errCd": 0, "result": result})


ADDRESS = [{"sido_cd": "11", "sgg_cd": "680", "emdong_cd": "550",
            "full_addr": "서울특별시 강남구 역삼동"}]


class TestSGIS(unittest.TestCase):
    def client(self, *responses):
        session = Mock()
        session.get.side_effect = responses
        return SGISHouseholdClient("test-id", "test-secret", session=session), session

    def test_missing_credentials(self):
        with self.assertRaises(SGISError):
            SGISHouseholdClient("id", "")

    def test_verified_households_and_cache(self):
        client, session = self.client(
            ok({"accessToken": "token"}), ok(ADDRESS),
            ok([{"adm_cd": "11680550", "adm_nm": "역삼1동", "household_cnt": "7100"}]),
            ok(ADDRESS))
        a = client.get_sgis_population(37.5, 127)
        b = client.get_sgis_population(37.5001, 127.0001)
        self.assertEqual(a.households, 7100)
        self.assertEqual(a, b)
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual(session.get.call_args_list[2].kwargs["params"]["low_search"], "0")

    def test_missing_or_suppressed_data(self):
        for value in ("N/A", None, "-1", "6200.5"):
            with self.subTest(value=value):
                client, _ = self.client(ok({"accessToken": "token"}), ok(ADDRESS),
                                        ok([{"adm_cd": "11680550", "household_cnt": value}]))
                self.assertIsNone(client.get_sgis_population(37.5, 127))

    def test_wrong_administrative_dong(self):
        client, _ = self.client(ok({"accessToken": "token"}), ok(ADDRESS),
                                ok([{"adm_cd": "11680560", "household_cnt": "8000"}]))
        self.assertIsNone(client.get_sgis_population(37.5, 127))

    def test_empty_reverse_geocode(self):
        client, _ = self.client(ok({"accessToken": "token"}), ok([]))
        self.assertIsNone(client.get_sgis_population(37.5, 127))

    def test_api_and_transport_failure(self):
        client, _ = self.client(Response({"errCd": -1}))
        with self.assertRaises(SGISError):
            client.get_sgis_population(37.5, 127)
        client, _ = self.client(Response(error=requests.Timeout()))
        with self.assertRaises(SGISError):
            client.get_sgis_population(37.5, 127)

    def test_grade_boundaries(self):
        cases = [(None, 1, None), (4999, 1, None), (5000, 0, "C급지"),
                 (5999, 1, "C급지"), (6000, 0, "B급지"),
                 (7000, 0, "B급지"), (7000, 1, "A급지")]
        for households, churches, expected in cases:
            self.assertEqual(classify_site(households, churches), expected)


if __name__ == "__main__":
    unittest.main()
