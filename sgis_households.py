"""SGIS census household lookup for the administrative dong containing a WGS84 point."""

from dataclasses import dataclass
import math

import requests


API_BASE = "https://sgisapi.mods.go.kr/OpenAPI3"
DEFAULT_CENSUS_YEAR = "2024"  # Latest year listed in the checked SGIS household API docs.


class SGISError(RuntimeError):
    """SGIS could not be contacted or returned an invalid/API-error response."""


@dataclass(frozen=True)
class HouseholdStatistic:
    households: int
    adm_cd: str
    adm_nm: str
    year: str


class SGISHouseholdClient:
    """Authenticate once per analysis and cache statistics by administrative dong."""

    def __init__(self, consumer_key, consumer_secret, year=DEFAULT_CENSUS_YEAR, session=None):
        if not consumer_key or not consumer_secret:
            raise SGISError("SGIS 서비스 ID와 Secret을 모두 설정해야 합니다.")
        if not str(year).isdigit() or not 2015 <= int(year) <= 2024:
            raise SGISError("SGIS 통계 기준연도는 2015~2024년으로 설정해야 합니다.")
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.year = str(year)
        self.session = session if session is not None else requests.Session()
        self.access_token = None
        self.households_by_dong = {}

    def _request(self, path, params):
        try:
            response = self.session.get(f"{API_BASE}{path}", params=params, timeout=5)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise SGISError("SGIS API 통신에 실패했습니다.") from exc
        if not isinstance(payload, dict) or str(payload.get("errCd")) != "0":
            raise SGISError("SGIS API가 오류 응답을 반환했습니다. 인증 및 요청 조건을 확인하세요.")
        return payload.get("result")

    def authenticate(self):
        if self.access_token:
            return
        result = self._request(
            "/auth/authentication.json",
            {"consumer_key": self.consumer_key, "consumer_secret": self.consumer_secret},
        )
        if not isinstance(result, dict) or not result.get("accessToken"):
            raise SGISError("SGIS 인증 응답에 유효한 토큰이 없습니다.")
        self.access_token = result["accessToken"]

    def get_sgis_population(self, lat, lng):
        """Return actual *administrative-dong households*, not 500 m households.

        None represents missing, suppressed or malformed statistics; no fallback
        number is fabricated. API/network failures raise SGISError.
        """
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lat, lng)):
            return None
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None
        self.authenticate()
        address = self._request(
            "/addr/rgeocodewgs84.json",
            {
                "accessToken": self.access_token,
                "x_coor": lng,
                "y_coor": lat,
                "addr_type": "20",
            },
        )
        if not isinstance(address, list) or not address or not isinstance(address[0], dict):
            return None
        item = address[0]
        parts = [str(item.get(k, "")).strip() for k in ("sido_cd", "sgg_cd", "emdong_cd")]
        if any(not part.isdigit() or len(part) != size for part, size in zip(parts, (2, 3, 3))):
            return None
        adm_cd = "".join(parts)
        if adm_cd in self.households_by_dong:
            return self.households_by_dong[adm_cd]

        result = self._request(
            "/stats/household.json",
            {
                "accessToken": self.access_token,
                "year": self.year,
                "adm_cd": adm_cd,
                "low_search": "0",
            },
        )
        statistic = None
        if isinstance(result, list):
            for row in result:
                if not isinstance(row, dict) or str(row.get("adm_cd")) != adm_cd:
                    continue
                raw_count = row.get("household_cnt")
                if isinstance(raw_count, bool) or not str(raw_count).isdigit():
                    break  # N/A, suppressed, or invalid census data.
                count = int(raw_count)
                statistic = HouseholdStatistic(
                    households=count,
                    adm_cd=adm_cd,
                    adm_nm=str(row.get("adm_nm") or item.get("full_addr") or adm_cd),
                    year=self.year,
                )
                break
        self.households_by_dong[adm_cd] = statistic
        return statistic


def classify_site(households, church_count):
    """Preserve the original A/B/C rules, but only for verified household counts."""
    if isinstance(households, bool) or not isinstance(households, int) or households < 5000:
        return None
    if households >= 7000 and church_count > 0:
        return "A급지"
    if households >= 6000:
        return "B급지"
    return "C급지"
