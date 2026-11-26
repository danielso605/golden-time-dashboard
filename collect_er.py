"""
[실제 데이터 1] 전국 응급의료기관 목록 수집  (수업: 공공데이터 open API 크롤링 방식)
------------------------------------------------------------------------------
공공데이터포털(www.data.go.kr)에서 아래 서비스를 '활용신청' 합니다.
    국립중앙의료원_전국 응급의료기관 정보 조회 서비스
    → 상세기능: 응급의료기관 목록정보 조회 (getEgytListInfoInqire)

마이페이지 > 일반 인증키(Encoding) 를 아래 ServiceKey 에 붙여 넣으세요.
(URL 문자열에 직접 붙이므로 수업 예제처럼 Encoding 키를 사용합니다)

실행:  python collect_er.py
결과:  data/processed/er.json  (수업 예제처럼 JSON 저장)
       data/processed/er.csv   (대시보드가 읽는 파일: name, sido, grade, lat, lon)
"""
import os
import urllib.request
import datetime
import json
import xml.etree.ElementTree as ET
import pandas as pd

# ⚠ GitHub에 키가 올라가지 않도록, 가능하면 환경변수(DATA_GO_KR_KEY)로 넣으세요.
ServiceKey = os.environ.get("DATA_GO_KR_KEY", "여기에_Encoding_인증키를_붙여넣으세요")

SIDO_FIX = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "전남광주": "전남광주통합특별시", "광주": "전남광주통합특별시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충청북": "충청북도", "충북": "충청북도",
    "충청남": "충청남도", "충남": "충청남도", "전라북": "전북특별자치도", "전북": "전북특별자치도",
    "전라남": "전남광주통합특별시", "전남": "전남광주통합특별시", "경상북": "경상북도", "경북": "경상북도",
    "경상남": "경상남도", "경남": "경상남도", "제주": "제주특별자치도",
}
GRADES = ["권역응급의료센터", "지역응급의료센터", "지역응급의료기관"]


# [CODE 1] URL에 접속해서 응답을 문자열로 받기 (수업 예제와 동일)
def getRequestUrl(url):
    req = urllib.request.Request(url)
    try:
        response = urllib.request.urlopen(req, timeout=30)
        if response.getcode() == 200:
            print("[%s] Url Request Success" % datetime.datetime.now())
            return response.read().decode('utf-8')
    except Exception as e:
        print(e)
        print("[%s] Error for URL : %s" % (datetime.datetime.now(), url))
        return None


# [CODE 2] 한 페이지 요청하기 → 파이썬 리스트(dict 목록)로 돌려주기
def getEmergencyItem(pageNo, numOfRows=500):
    service_url = "http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEgytListInfoInqire"
    parameters = "?_type=json&serviceKey=" + ServiceKey   # 인증키
    parameters += "&pageNo=" + str(pageNo)
    parameters += "&numOfRows=" + str(numOfRows)
    url = service_url + parameters
    print(url)   # 액세스 거부 여부 확인용 출력
    retData = getRequestUrl(url)
    if retData is None:
        return None, 0

    # 이 서비스는 JSON 대신 XML로 응답하는 경우가 있어서 두 가지를 모두 처리
    if retData.strip().startswith("{"):
        jsonData = json.loads(retData)
        body = jsonData['response']['body']
        items = body['items']['item'] if body['items'] else []
        if isinstance(items, dict):        # 1건이면 dict 로 옴
            items = [items]
        return items, int(body['totalCount'])
    else:
        root = ET.fromstring(retData)
        items = [{child.tag: child.text for child in it} for it in root.iter('item')]
        return items, int(root.findtext('.//totalCount') or 0)


# [CODE 3] 전체 페이지를 돌면서 필요한 항목만 모으기
def getEmergencyService():
    jsonResult, result = [], []
    pageNo = 1
    while True:
        items, total = getEmergencyItem(pageNo)
        if not items:
            break
        for it in items:
            name = it.get('dutyName')
            addr = it.get('dutyAddr', '')
            grade = it.get('dutyEmclsName')
            lat, lon = it.get('wgs84Lat'), it.get('wgs84Lon')
            jsonResult.append({'name': name, 'addr': addr, 'grade': grade, 'lat': lat, 'lon': lon})
            result.append([name, addr, grade, lat, lon])
        print('[ %d 페이지 : 누적 %d / %d ]' % (pageNo, len(result), total))
        if len(result) >= total:
            break
        pageNo += 1
    return jsonResult, result


def to_sido(addr):
    first = str(addr).split()[0] if addr else ""
    for k, v in SIDO_FIX.items():
        if first.startswith(k):
            return v
    return first


def main():
    print("<< 전국 응급의료기관 목록을 수집합니다. >>")
    jsonResult, result = getEmergencyService()
    os.makedirs("data/processed", exist_ok=True)

    # 안전장치: 받아 온 기관이 너무 적으면(키 오류·응답 실패) 기존 파일을 덮어쓰지 않는다
    MIN_COUNT = 100
    if len(result) < MIN_COUNT:
        print("[경고] 응급의료기관을 %d건밖에 받지 못했습니다. 인증키(DATA_GO_KR_KEY)나 API 응답을 확인하세요." % len(result))
        print("       기존 data/processed/er.csv 는 그대로 두고 종료합니다.")
        return

    # 파일저장 1 : json 파일
    with open('data/processed/er.json', 'w', encoding='utf8') as outfile:
        outfile.write(json.dumps(jsonResult, indent=4, ensure_ascii=False))

    # 파일저장 2 : csv 파일 (대시보드용으로 정리)
    df = pd.DataFrame(result, columns=["name", "addr", "grade", "lat", "lon"])
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["sido"] = df["addr"].map(to_sido)
    print("등급별 개수(원본):\n", df["grade"].value_counts())
    df = df.dropna(subset=["lat", "lon"])
    df = df[df["grade"].isin(GRADES)]        # 3개 등급만 사용
    if len(df) < MIN_COUNT:
        print("[경고] 정리 후 %d건만 남았습니다. 기존 er.csv 는 그대로 둡니다." % len(df))
        return
    tmp = 'data/processed/er_tmp.csv'                 # 임시 파일에 먼저 쓰고, 끝까지 성공하면 교체
    df[["name", "sido", "grade", "lat", "lon"]].to_csv(tmp, index=False, encoding='utf-8-sig')
    os.replace(tmp, 'data/processed/er.csv')
    print("저장 완료: %d건 → data/processed/er.csv" % len(df))


if __name__ == '__main__':
    main()
