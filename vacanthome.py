import os
import json
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import streamlit as st
from io import BytesIO
import base64
import requests
import numpy as np

# vworld API 키
vworld_key = "202159BE-213A-3469-B34A-8C042106E69E"

# Streamlit 앱 설정
st.title("부산광역시 빈집 분포도")
st.markdown("엑셀 파일을 업로드하면 건물 정보의 위치와 사진이 지도에 표시됩니다.")

# 데이터프레임 초기화
df = pd.DataFrame()

# 사이드바에서 엑셀 파일 업로드
uploaded_file = st.sidebar.file_uploader("건물 정보가 담긴 엑셀 파일을 업로드하세요.", type=["xlsx"])

# 사이드바에서 사진 파일 업로드
uploaded_images = st.sidebar.file_uploader("사진 파일을 업로드하세요.", type=["jpg", "png"], accept_multiple_files=True)

# GeoJSON URL
geojson_base_url = "https://raw.githubusercontent.com/raqoon886/Local_HangJeongDong/master/hangjeongdong_부산광역시.geojson"
response = requests.get(geojson_base_url)

if response.status_code == 200:
    geojson_data = response.json()
else:
    st.error("GeoJSON 파일을 불러오는 데 오류가 발생했습니다.")
    st.stop()

# Mapping `시군구` names to `sgg` codes
sgg_mapping = {
    "중구": "26110",
    "서구": "26140",
    "동구": "26170",
    "영도구": "26200",
    "부산진구": "26230",
    "동래구": "26260",
    "남구": "26290",
    "북구": "26320",
    "해운대구": "26350",
    "사하구": "26380",
    "금정구": "26410",
    "강서구": "26440",
    "연제구": "26470",
    "수영구": "26500",
    "사상구": "26530",
    "기장군": "26710"
}

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)

        # 데이터 검증: 필요한 열이 존재하는지 확인
        required_columns = ['주소명', '위도', '경도', '주택유형', '면적', '시군구', '사진 경로']
        if not all(col in df.columns for col in required_columns):
            st.error("엑셀 파일에 필수 열이 없습니다.")
        else:
            st.write("업로드된 데이터:")
            st.write(df)

            # 위도와 경도 열의 데이터 형식을 숫자형으로 변환 (문자열이 있으면 NaN으로 처리)
            df['위도'] = pd.to_numeric(df['위도'], errors='coerce')
            df['경도'] = pd.to_numeric(df['경도'], errors='coerce')

            # 유효하지 않은 위도 및 경도 행 제거
            df = df.dropna(subset=['위도', '경도'])

            # 필터 옵션 추출
            시군구_options = df['시군구'].unique().tolist()
            주택유형_options = df['주택유형'].unique().tolist()

    except Exception as e:
        st.error(f"엑셀 파일을 읽는 중 오류 발생: {e}")

    # '부산시 전체' 옵션을 추가
    selected_시군구 = st.sidebar.multiselect("시군구 선택 (부산시 전체 포함)", ['부산시 전체'] + 시군구_options)
    selected_주택유형 = st.sidebar.multiselect("주택유형 선택", 주택유형_options)

    # Convert selected `시군구` names to their corresponding `sgg` codes
    selected_sgg_codes = []
    if "부산시 전체" in selected_시군구:
        selected_sgg_codes = list(sgg_mapping.values())
    else:
        selected_sgg_codes = [sgg_mapping[sgg] for sgg in selected_시군구 if sgg in sgg_mapping]

    # 필터링
    filtered_df = df.copy()

    if selected_시군구:
        if "부산시 전체" in selected_시군구:
            filtered_df = filtered_df
        else:
            filtered_df = filtered_df[filtered_df['시군구'].isin(selected_시군구)]

    if selected_주택유형:
        filtered_df = filtered_df[filtered_df['주택유형'].isin(selected_주택유형)]

    # 초기 지도 생성
    initial_zoom_level = 11
    map_center = [filtered_df['위도'].mean(), filtered_df['경도'].mean()]
    m = folium.Map(location=map_center, zoom_start=initial_zoom_level)

    layer = "white"
    tileType = "png"
    tiles = f"https://api.vworld.kr/req/wmts/1.0.0/{vworld_key}/{layer}/{{z}}/{{y}}/{{x}}.{tileType}"
    attr = "Vworld"

    folium.TileLayer(tiles=tiles, attr=attr, overlay=True, control=True).add_to(m)

    # Choropleth 지도 생성
    if not filtered_df.empty:
        sgg_counts = filtered_df['시군구'].value_counts().reset_index()
        sgg_counts.columns = ['시군구', 'count']
        sgg_counts['sgg'] = sgg_counts['시군구'].map(sgg_mapping)

        # Count가 1보다 큰 경우만 binning, 최소 2개 이상의 고유한 값이 필요
        unique_counts = sgg_counts['count'].unique()
        if len(unique_counts) > 1:  # 최소 2개 이상의 고유한 값이 있는지 확인
            count_bins = pd.qcut(sgg_counts['count'], 7, labels=False)
        else:
            count_bins = [0] * len(sgg_counts)  # 모두 동일한 bin으로 변환

        # GeoJSON 레이어 추가
        folium.GeoJson(
            geojson_data,
            name='자치구',
            style_function=lambda feature: {
                'fillColor': 'white',  # 기본 색상
                'color': 'white',
                'weight': 1.4,
                'fillOpacity': 0.1
            }
        ).add_to(m)

        # Choropleth 추가
        folium.Choropleth(
            geo_data=geojson_data,
            data=sgg_counts,
            columns=['sgg', 'count'],
            key_on='feature.properties.sgg',
            fill_color='Greens',
            fill_opacity=0.5,
            line_opacity=0.2,
            bins=7,
            legend_name='Count of Buildings'
        ).add_to(m)

        # 시군구별 MarkerCluster 생성
        clusters = {}
        image_dict = {}
        if uploaded_images:
            for img in uploaded_images:
                image_dict[img.name] = img.read()

        for idx, row in filtered_df.iterrows():
            if pd.notnull(row['위도']) and pd.notnull(row['경도']):
                sgg_code = sgg_mapping[row['시군구']]

                # 클러스터가 생성되지 않았다면 추가
                if sgg_code not in clusters:
                    clusters[sgg_code] = MarkerCluster(max_cluster_radius=75)
                    clusters[sgg_code].add_to(m)

                # Popup 내용 생성
                image_name = row['사진 경로']
                img_data = image_dict.get(image_name)
                all_images_html = ""

                if img_data is not None:
                    img_base64 = base64.b64encode(img_data).decode()
                    all_images_html += f"<img src='data:image/jpeg;base64,{img_base64}' style='width:100px; height:auto;'>"

                # Popup 내용 생성
                popup_text = (f"<div style='font-family: sans-serif; font-size: 12px;'>"
                              f"<b>[주소명] {row['주소명']}</b><br>"
                              f"[주택유형] {row['주택유형']}<br>"
                              f"[면적] {row['면적']} m²<br>"
                              f"</div>"
                              f"<div style='padding-top: 5px;'>"
                              f"{all_images_html}"
                              f"</div>")

                folium.Marker(location=[row['위도'], row['경도']],
                              popup=folium.Popup(popup_text, max_width=300),
                              tooltip=f"주소명: {row['주소명']}").add_to(clusters[sgg_code])

        # HTML 파일을 메모리에서 바이너리로 저장
        html_data = BytesIO()
        m.save(html_data, close_file=False)

        # HTML 데이터를 Streamlit에 표시
        st.components.v1.html(html_data.getvalue().decode('utf-8'), height=500)

        # 다운로드 버튼
        st.download_button(label="HTML 파일 다운로드",
                           data=html_data.getvalue(),
                           file_name="map.html",
                           mime="text/html")
    else:
        st.write("선택한 조건에 대한 정보가 없습니다.")
