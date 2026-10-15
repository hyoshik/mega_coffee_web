# SGIS 데이터 설정 및 검증

가구 수는 **SGIS 인구주택총조사의 행정동 전체 가구 수**입니다. 지도에 표시하는 반경 500m의 가구 수가 아닙니다. 5,000 / 6,000 / 7,000 기준은 기존 서비스의 임의 규칙이며, 실제 매출 예측모델로 검증된 기준은 아닙니다.

## 설정

SGIS 개발지원센터(https://sgis.mods.go.kr/developer/)에서 API 이용신청 후 서비스 ID(consumer_key), Secret(consumer_secret)을 발급받고 필요한 API 사용 권한을 확인합니다. 카카오 개발자 사이트에서 REST API 키를 발급받습니다. 다음 키는 **GitHub에 커밋하지 않고** 배포 서비스의 환경변수나 Streamlit Secrets에서 설정합니다.

```toml
KAKAO_REST_API_KEY = "your-kakao-rest-key"
SGIS_CONSUMER_KEY = "your-sgis-key"
SGIS_CONSUMER_SECRET = "your-sgis-secret"
SGIS_CENSUS_YEAR = "2024"
```

Streamlit Community Cloud에서는 앱 설정의 Secrets에 추가할 수 있습니다. 개발 환경에서는 위 키를 환경변수로도 설정할 수 있습니다. 기존 저장소에 노출되어 있던 카카오 키와 SGIS ID는 재발급하거나 사용 상태를 점검하는 것이 좋습니다.

SGIS 호출 순서: `/OpenAPI3/auth/authentication.json` → `/OpenAPI3/addr/rgeocodewgs84.json` (`addr_type=20`) → `/OpenAPI3/stats/household.json` (`adm_cd` 8자리, `low_search=0`, `year=2024`).

SGIS API가 2024년까지 가구 통계 연도를 제공하는 것으로 확인되어 기본값을 2024로 설정했습니다. API가 지원하는 최신 연도와 행정동 코드의 기준연도 일치 여부를 운영 전 확인하십시오.

## 판정 규칙

기존 매장 250m 이내 후보 제외 → 학교 500m 이내 후보만 대상 → **SGIS 행정동 가구 수 5,000 미만 제외** → 가구 수 7,000 이상이고 교회 200m 이내이면 A, 그 외 6,000 이상이면 B, 나머지는 C. 가구 수가 누락되거나 인증/네트워크 오류가 발생하면 A/B/C 등급을 매기지 않고 회색 마커와 '등급 보류'로 표시합니다.

학교·교회·메가커피 검색은 기존 카카오 API 로직을 사용하고 Folium 지도, 기존 매장/학교/추천지 마커, 250m 및 500m 원을 유지합니다. 카카오 API 자체의 호출 실패 여부는 기존 코드처럼 세밀하게 검증하지 않으므로 실제 서비스 운영 전 추가 검증이 필요합니다.

## 테스트

```sh
python -m unittest discover -s tests -v
python -m py_compile app_web.py sgis_households.py
```

모의 API 응답으로 조회/인증 오류, 통계 누락, 행정동 불일치, 같은 행정동 캐시, 등급 경계값을 확인합니다. 실제 SGIS 호출은 별도 유효한 비밀키와 사용승인이 필요하며 테스트는 실제 가구 수의 정확성을 보증하지 않습니다.

자료: https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/census.html 및 https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/addressBoundary.html
