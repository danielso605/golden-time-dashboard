# 우리 동네는 골든타임 안에 있을까?
### 전국 응급의료 사각지대 지도와 응급실 신설 효과 시뮬레이션

공공데이터(응급의료기관 위치 + 시군구 인구)로 **응급실까지 예상 이동시간**을 계산하고,
골든타임 밖에 사는 인구(사각지대)를 지도·그래프로 보여주는 **Flask 웹 대시보드**입니다.
가상의 응급실을 세웠을 때 사각지대가 얼마나 줄어드는지도 시뮬레이션할 수 있습니다.

| 과제 항목 | 이 프로젝트 |
|---|---|
| 제출형태 | **형태 3**: 콘트롤이 있는 웹페이지 대시보드 + Docker + GitHub |
| 콘트롤 | 콤보박스 5개(시도, 골든타임 기준, 그래프 방식, 우리 동네, 신설 위치), 버튼 6개 |
| 사용 패키지 | pandas, numpy, matplotlib, seaborn, mpld3, Flask, (수집) urllib, json, requests |
| 그래프 | 13개 (서로 다른 종류 11가지) + 표 3개 + OpenStreetMap 지도(iframe) |
| 웹 게시 | Flask 웹페이지 (python 출력 화면 아님) |

---

## 1. 폴더 구조

```
golden-time-dashboard/
├── app.py               # Flask 웹서버 (라우트, 컨트롤 처리, mpld3 변환)
├── analysis.py          # 거리·이동시간 계산, 사각지대 판정, 시뮬레이션, 추천
├── charts.py            # 그래프 13개 + 그래프마다 설명 문장
├── templates/index.html # 웹페이지 (form, select, button, table, iframe)
├── static/style.css     # 디자인
├── collect_er.py        # [실제 데이터] 응급의료기관 Open API 수집 (urllib + json)
├── prepare_population.py # [실제 데이터] KOSIS 인구 파일 정리 (총인구·65세+·0~14세)
├── prepare_regions.py   # [실제 데이터] 시군구 좌표 찾기 (카카오)
├── make_sample_data.py  # 연습용 가상 데이터 생성
├── data/sample/         # 가상 데이터 (처음엔 이걸로 실행됨)
├── data/processed/      # 실제 데이터를 만들면 여기 저장 → 자동으로 이걸 사용
├── requirements.txt
└── Dockerfile
```

## 2. 바로 실행해 보기 (샘플 데이터)

```bash
pip install -r requirements.txt
python app.py
```
브라우저에서 **http://127.0.0.1:5000** 접속.
처음에는 `data/sample`의 **가상 데이터**로 실행됩니다. 화면 위에 노란 안내가 보이면 샘플 모드입니다.

## 3. 실제 데이터로 바꾸기 (보고서 제출 전 필수)

### 3-1. 응급의료기관 (공공데이터포털 Open API)
1. data.go.kr 로그인 → **"국립중앙의료원_전국 응급의료기관 정보 조회 서비스"** 활용신청
2. 마이페이지에서 **일반 인증키(Encoding)** 복사
3. 실행
   ```bash
   # Windows PowerShell
   $env:DATA_GO_KR_KEY="복사한키"; python collect_er.py
   ```
   → `data/processed/er.json`, `data/processed/er.csv` 생성
   (수업의 '출입국관광통계' 예제와 같은 구조: `getRequestUrl()` → `getEmergencyItem()` → `getEmergencyService()` → JSON/CSV 저장)

### 3-2. 시군구 인구 정리 (KOSIS)
1. KOSIS → **"행정구역(시군구)별/1세별 주민등록인구"** (항목: 총인구수, 행정구역: 시군구까지 전체, 연령: 전체, 시점: 1개) → EXCEL 다운로드
2. 다운로드한 파일을 그대로 넣어 실행 (이미 정리된 `data/raw/population.csv`가 있다면 건너뛰기)
   ```bash
   python prepare_population.py "다운로드한파일.xls"
   ```
   → `data/raw/population.csv` (시도, 시군구, 총인구, 65세 이상, 0~14세)
   - 출장소(인구 0) 제거, 일반구가 있는 시는 구 단위로 분리, 전남광주통합특별시 반영

### 3-3. 시군구 좌표 찾기 (카카오)
developers.kakao.com 에서 앱을 만들고 **REST API 키**를 받아 실행
```bash
$env:KAKAO_REST_KEY="키"; python prepare_regions.py
```
→ `data/processed/regions.csv` 생성 (새로 생긴 구는 대표 동네 좌표로 대신 찾음)

두 파일이 생기면 `python app.py`를 다시 실행했을 때 **자동으로 실제 데이터**를 사용합니다.

> ⚠ 인증키를 코드에 직접 적었다면 GitHub에 올리기 전에 지우세요.

## 4. 분석 방법

0. **취약계층**: 고령인구 = 65세 이상, 어린이 = 0~14세 (KOSIS 1세별 인구 합산)
1. **이동시간** = 직선거리(하버사인 공식) × 도로 보정계수 1.4 ÷ 평균속도 45km/h × 60
   (`analysis.py` 맨 위 `DETOUR`, `SPEED` 값을 바꿔서 민감도 분석 가능)
2. **골든타임 기준** (보건복지부 응급의료 취약지 기준 참고)
   - 지역응급의료센터 이상 30분 / 권역응급의료센터 60분 / 모든 응급의료기관 30분
3. **사각지대** = 기준 시간 안에 해당 등급 기관에 도착할 수 없는 지역(인구)
4. **신설 시뮬레이션** = 사각지대 지역에 가상의 응급의료센터를 추가한 뒤 다시 계산
5. **최적 위치 추천** = 사각지대 인구를 가장 많이 줄이는 곳을 하나씩 고르는 탐욕(greedy) 알고리즘

## 5. 그래프 목록 (보고서 1페이지 "그래프 수" 작성용)

대시보드는 **질문 세 개 + 해결책** 순서로 구성됩니다. 그래프 제목은 결론 문장이고(숫자 자동 반영), 모든 그래프 위에 "축 읽는 법"이 있습니다.

| 번호 | 질문 | 그래프 | 종류 | 함수 |
|---|---|---|---|---|
| 1 | 어디가? | 응급의료 사각지대 지도 | 지도형 산점도 + 국토 윤곽 | `plt.scatter`, `Polygon` |
| 2 | 어디가? | 시도별 골든타임 밖 인구 비율 | 가로 막대 | `plt.barh` |
| 3 | 어디가? | 권역별 누적 도달 인구 비율 | 누적 선그래프 | `plt.plot` |
| 4 | 어디가? | 시도별 이동시간 구성 | 100% 누적 가로 막대 | `plt.barh(left=...)` |
| 5 | 누가? | 취약계층(고령·어린이)별 사각지대 비율 | 묶은 막대 | `plt.bar` |
| 6 | 누가? | 고령인구 비율과 이동시간 (상관·회귀) | 회귀 산점도 | `plt.scatter`, `np.polyfit`, `np.corrcoef` |
| 7 | 누가? | 시·구 vs 군 지역 이동시간 | 커널밀도 그래프 | `sns.kdeplot` |
| 8 | 왜? | 시도별 응급의료기관 등급 구성 | 누적 가로 막대 | `plt.barh` |
| 9 | 왜? | 인구 10만 명당 응급의료기관 수 | 세로 막대 | `plt.bar` |
| 10 | 왜? | 사각지대 주변 응급의료기관 수 | 롤리팝 차트 | `plt.hlines`, `plt.scatter` |
| 11 | 왜? | 지역 특성 간 상관계수 | 히트맵 | `df.corr()`, `sns.heatmap` |
| 12 | 어떻게? | 신설 전후 비교 (전체·고령·어린이) | 묶은 막대 | `plt.bar` |
| 13 | 어떻게? | 신설 후 사각지대 지도 | 지도형 산점도 | `plt.scatter` |

모든 그래프 아래에 설명 3줄(읽는 법 / 해석 / 이번 결과)이 있고, 마지막 줄 숫자는 콤보박스 선택에 따라 바뀝니다.
섬 지역(옹진군, 울릉군)은 바다 위 직선거리로 계산되어 실제와 차이가 크므로, 회귀·밀도·상관 그래프에서는 제외하고 지도에는 작은 박스로 따로 표시합니다.

## 6. mpld3 와 PNG
- 기본은 **이미지(PNG)** 입니다. 수업 Dash 예제의 `BytesIO` + `base64` 방법으로 그려서 글자·범례·기준선이 정확하게 보입니다.
- **인터랙티브(mpld3)** 를 고르면 수업 방식대로 `mpld3.fig_to_html(fig)`로 확대·이동이 가능한 그래프가 됩니다.
  다만 mpld3는 범례, 막대 눈금 이름(시도 이름), 기준선 위치를 잘못 그리는 경우가 있어서, 깨지지 않는 선·점 그래프(6번 회귀 산점도)에만 적용하고 나머지는 PNG로 보여줍니다.

## 7. Docker

```bash
docker build -t golden-time .
docker run -p 5000:5000 golden-time
```
→ http://localhost:5000

## 8. GitHub

```bash
git init
git add .
git commit -m "골든타임 사각지대 대시보드"
git branch -M main
git remote add origin https://github.com/<내아이디>/golden-time-dashboard.git
git push -u origin main
```

## 9. 한계
- 시군구를 대표 좌표(점 하나)로 보기 때문에 같은 시군구 안 외곽 마을은 실제보다 가깝게 계산될 수 있음
- 실제 도로망, 교통 체증, 섬 지역의 배·헬기 이송, 응급실 병상 포화는 반영하지 않음
- 응급의료기관 목록은 수집 시점 기준이며, 운영 상태는 바뀔 수 있음
