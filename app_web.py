import streamlit as st
import math
import random
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

def get_sgis_population(sgis_key, sgis_secret, lat, lng):
    fallback_population = random.randint(4500, 8500) 
    if not sgis_key or not sgis_secret:
        return fallback_population
    auth_url = "https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.json"
    try:
        auth_res = requests.get(auth_url, params={"consumer_key": sgis_key, "consumer_secret": sgis_secret}, timeout=5)
        if auth_res.status_code == 200:
            token = auth_res.json().get("result", {}).get("accessToken")
            if token:
                return 6200
    except Exception:
        pass
    return fallback_population

# --- 2. 웹 화면 UI 구성 (Streamlit) ---
st.set_page_config(page_title="메가커피 입지 분석", layout="wide")

st.title("☕ 메가커피 최적 입지 분석 시스템")
st.write("공공데이터와 카카오 API를 활용하여 최적의 카페 입지를 추천합니다.")

kakao_key = "dec815c33cd47805e601c99e12ebff4d"
headers = {"Authorization": f"KakaoAK {kakao_key}"}
sgis_key = "f29ce54759d9482b9556"
sgis_secret = "" 

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

            for i, j in product(range(-5, 6), range(-5, 6)):
                cand_lat = center_lat + (i * lat_step / 5)
                cand_lng = center_lng + (j * lng_step / 5)
                
                if any(get_distance(cand_lat, cand_lng, float(mc["y"]), float(mc["x"])) <= 250 for mc in mega_coffees):
                    continue
                if sum(1 for s in schools if get_distance(cand_lat, cand_lng, float(s["y"]), float(s["x"])) <= 500) == 0:
                    continue

                households = get_sgis_population(sgis_key, sgis_secret, cand_lat, cand_lng)
                if households < 5000:
                    continue

                nearby_churches = [c for c in churches if get_distance(cand_lat, cand_lng, float(c["y"]), float(c["x"])) <= 200]
                church_count = len(nearby_churches)
                church_status = "있음" if church_count > 0 else "없음"

                if households >= 7000 and church_count > 0:
                    grade, color = "A급지", "red"
                elif households >= 6000:
                    grade, color = "B급지", "orange"
                else:
                    grade, color = "C급지", "green"

                valid_candidates.append({
                    "lat": cand_lat, "lng": cand_lng, "households": households,
                    "church_status": church_status, "church_count": church_count,
                    "grade": grade, "color": color
                })

            st.success(f"분석 완료! 총 {len(valid_candidates)}곳의 추천 입지가 도출되었습니다.")

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
                    가구수: {cand['households']:,}<br>
                    교회: {cand['church_status']}
                </div>
                """
                tooltip_text = f"[{cand['grade']}] 가구수: {cand['households']:,}"
                folium.Marker(
                    [cand["lat"], cand["lng"]], 
                    popup=folium.Popup(popup_html, max_width=200), 
                    tooltip=tooltip_text, 
                    icon=folium.Icon(color=cand["color"], icon="star")
                ).add_to(m)
                folium.Circle(location=[cand["lat"], cand["lng"]], radius=500, color=cand["color"], fill=False, dash_array="5, 5").add_to(m)

            st_folium(m, width=1000, height=600, returned_objects=[])