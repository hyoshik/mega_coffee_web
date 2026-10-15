import streamlit as st
import math
import os
from sgis_households import SGISError, SGISHouseholdClient, DEFAULT_CENSUS_YEAR, classify_site
from itertools import product
import folium
import requests
from streamlit_folium import st_folium

# --- 1. 유틸리티 함수 ---
def get_distance(lat1, lon1, lat2, lon2):
    R = 6371000  
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_location_center(address_or_keyword, headers):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    params = {"query": address_or_keyword, "size": 1}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        if res.status_code == 200 and res.json().get("documents"):
            doc = res.json()["documents"][0]
            return float(doc["y"]), float(doc["x"])
    except Exception:
        pass
    return None, None

def search_places_all(keyword, lat, lng, headers, radius=2000):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    results = []
    try:
        for page in range(1, 4):
            params = {"query": keyword, "y": lat, "x": lng, "radius": radius, "size": 15, "page": page}
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                data = res.json()
                results.extend(data.get("documents", []))
                if data.get("meta", {}).get("is_end", True):
                    break
            else:
                break
    except Exception:
        pass
    return results

# --- 2. 웹 화면 UI 구성 (Streamlit) ---
st.set_page_config(page_title="메가커피 입지 분석", layout="wide")

st.title("☕ 메가커피 최적 입지 분석 시스템")
st.write("공공데이터와 카카오 API를 활용하여 최적의 카페 입지를 추천합니다.")

kakao_key = os.getenv("KAKAO_REST_API_KEY") or st.secrets.get("KAKAO_REST_API_KEY", "")
headers = {"Authorization": f"KakaoAK {kakao_key}"}
sgis_key = os.getenv("SGIS_CONSUMER_KEY") or st.secrets.get("SGIS_CONSUMER_KEY", "")
sgis_secret = os.getenv("SGIS_CONSUMER_SECRET") or st.secrets.get("SGIS_CONSUMER_SECRET", "")
sgis_year = os.getenv("SGIS_CENSUS_YEAR") or st.secrets.get("SGIS_CENSUS_YEAR", DEFAULT_CENSUS_YEAR)

target_region = st.text_input("분석할 지역명을 입력하세요", "서울특별시 강남구")

# [핵심 수정] 프로그램 기억 장치(session_state) 세팅
if "run_analysis" not in st.session_state:
    st.session_state.run_analysis = False

# 버튼을 누르면 기억 장치에 'True(실행함)'로 저장
if st.button("분석 시작", type="primary"):
    st.session_state.run_analysis = True

# 버튼이 한 번이라도 눌려서 True 상태가 되었다면, 지도를 계속 화면에 유지함
if st.session_state.run_analysis:
    with st.spinner(f"'{target_region}' 주변 데이터를 분석하고 있습니다... (약 10~20초 소요)"):
        center_lat, center_lng = get_location_center(target_region, headers)

        if not center_lat:
            st.error("해당 지역의 좌표를 찾을 수 없습니다. 검색어를 확인해 주세요.")
        else:
            mega_coffees = search_places_all("메가커피", center_lat, center_lng, headers, 2000)
            schools = search_places_all("중학교", center_lat, center_lng, headers, 2000) + \
                      search_places_all("고등학교", center_lat, center_lng, headers, 2000)
            churches = search_places_all("교회", center_lat, center_lng, headers, 2000)

            lat_step, lng_step = 0.009, 0.011
            valid_candidates = []
            pending_candidates = []
            sgis_error = None
            try:
                sgis_client = SGISHouseholdClient(sgis_key, sgis_secret, sgis_year)
            except SGISError as exc:
                sgis_client = None
                sgis_error = str(exc)

            for i, j in product(range(-5, 6), range(-5, 6)):
                cand_lat = center_lat + (i * lat_step / 5)
                cand_lng = center_lng + (j * lng_step / 5)
                
                if any(get_distance(cand_lat, cand_lng, float(mc["y"]), float(mc["x"])) <= 250 for mc in mega_coffees):
                    continue
                if sum(1 for s in schools if get_distance(cand_lat, cand_lng, float(s["y"]), float(s["x"])) <= 500) == 0:
                    continue

                nearby_churches = [c for c in churches if get_distance(cand_lat, cand_lng, float(c["y"]), float(c["x"])) <= 200]
                church_count = len(nearby_churches)
                church_status = "있음" if church_count else "없음"
                statistic = None
                if sgis_client and not sgis_error:
                    try:
                        statistic = sgis_client.get_sgis_population(cand_lat, cand_lng)
                    except SGISError as exc:
                        sgis_error = str(exc)
                if statistic is None:
                    pending_candidates.append({"lat": cand_lat, "lng": cand_lng})
                    continue
                households = statistic.households
                grade = classify_site(households, church_count)
                if grade is None:
                    continue
                color = {"A급지": "red", "B급지": "orange", "C급지": "green"}[grade]

                valid_candidates.append({
                    "lat": cand_lat, "lng": cand_lng, "households": households,
                    "church_status": church_status, "church_count": church_count,
                    "grade": grade, "color": color, "statistic": statistic
                })

            if sgis_error:
                st.warning(f"SGIS 조회 실패: {sgis_error}. 가구 수 미확인 후보의 등급은 보류됩니다.")
            st.info(f"가구 수는 {sgis_year}년 SGIS 행정동 전체 가구 수입니다. 지도상 500m 원의 가구 수가 아닙니다.")
            st.success(f"검증된 추천 {len(valid_candidates)}곳 / 가구 수 미확인 {len(pending_candidates)}곳")

            m = folium.Map(location=[center_lat, center_lng], zoom_start=14)

            for mc in mega_coffees:
                folium.Marker([float(mc["y"]), float(mc["x"])], tooltip=f"메가커피: {mc['place_name']}", icon=folium.Icon(color="lightgray", icon="info-sign")).add_to(m)
                folium.Circle(location=[float(mc["y"]), float(mc["x"])], radius=250, color="gray", fill=True, fill_opacity=0.1).add_to(m)

            for school in schools:
                folium.Marker([float(school["y"]), float(school["x"])], tooltip=f"학교: {school['place_name']}", icon=folium.Icon(color="blue", icon="book")).add_to(m)

            for cand in valid_candidates:
                popup_html = f"""
                <div style="width:150px;">
                    <h4 style="color:{cand['color']}; margin-bottom:5px;"><b>{cand['grade']}</b></h4>
                    행정동 가구 수 ({cand['statistic'].year}년): {cand['households']:,}<br>행정동: {cand['statistic'].adm_nm}<br>
                    교회: {cand['church_status']}
                </div>
                """
                tooltip_text = f"[{cand['grade']}] 행정동 가구 수: {cand['households']:,}"
                folium.Marker(
                    [cand["lat"], cand["lng"]], 
                    popup=folium.Popup(popup_html, max_width=200), 
                    tooltip=tooltip_text, 
                    icon=folium.Icon(color=cand["color"], icon="star")
                ).add_to(m)
                folium.Circle(location=[cand["lat"], cand["lng"]], radius=500, color=cand["color"], fill=False, dash_array="5, 5").add_to(m)

            for cand in pending_candidates:
                folium.Marker([cand["lat"], cand["lng"]], tooltip="가구 수 미확인 · 등급 보류",
                              icon=folium.Icon(color="lightgray", icon="question-sign")).add_to(m)
            st_folium(m, width=1000, height=600, returned_objects=[])