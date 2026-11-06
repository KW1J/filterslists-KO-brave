# filterslists-KO for Brave

[`filterslists-KO`](https://github.com/FilteringDev/filterslists-KO)(한국어 광고·트래커 차단 필터 리스트)의
uBlock Origin 배포본을 **Brave(Shields, brave/adblock-rust 엔진)에서 실제로 동작하도록 변환**해
GitHub Actions로 자동 갱신하는 비공식 빌드입니다.

- 원본: `@filteringdev/filterslists-ko` npm 패키지의 `dist/resolved/filterslist-uBlockOrigin/ubo-chromium.txt`
- 갱신: GitHub Actions가 6시간마다 원본을 받아 변환 → `dist/`만 자동 커밋
- 검증: 변환된 규칙 전부를 **Brave와 같은 파서(adblock-rust 0.13.5)** 로 파싱해 거부 0건 확인

## 구독 URL

Brave 주소창에 `brave://settings/shields/filters` 를 열고 **Add filter list by URL** 에 아래 주소를 넣으세요.

```
https://raw.githubusercontent.com/KW1J/filterslists-KO-brave/main/dist/filterslists-KO-brave.txt
```

CDN 캐시를 쓰는 대체 주소(빠르지만 갱신이 몇 분~몇 시간 늦을 수 있음):

```
https://cdn.jsdelivr.net/gh/KW1J/filterslists-KO-brave@main/dist/filterslists-KO-brave.txt
```

> **중복 차단 주의 (선택)**
> Brave에 기본 내장된 **Korean website ad blocker**(`brave://settings/shields/filters` → Content filters)를
> 함께 켜 두면 같은 사이트에 규칙이 두 번 적용됩니다. 동작에 문제는 없지만 필터 디버깅이 어려워지므로
> 이 리스트를 쓰는 동안에는 내장 한국어 리스트를 꺼 두는 편을 권합니다.

## 왜 변환이 필요한가

filterslists-KO는 uBlock Origin 문법을 씁니다. Brave의 엔진(adblock-rust)은 uBO의 프로시저럴 연산자
(`:has-text`, `:matches-css`, `:upward`, `:remove()`, `:style()` 등)는 지원하지만, uBO의 **스타일 주입
표기**(`#$#`)와 **프로시저럴 본문 표기**(`#$?#`)는 파싱 단계에서 거부합니다. 그래서 원본을 그대로 넣으면
스타일/요소 제거 규칙 268건이 조용히 사라집니다.

이 저장소는 의미가 같은 ABP/Brave 표기로 기계적으로 옮깁니다.

| 원본 (uBO) | 변환 결과 (Brave) | 건수 |
|---|---|---:|
| `host#$#sel { color: red !important; }` | `host##sel:style(color: red !important;)` | 247 |
| `host#$?#sel { remove: true; }` | `host##sel:remove()` | 21 |
| `host#@$#…` / `host#@$?#…` | `host#@#sel:style(…)` / `:remove()` | 0 (현재 원본에 없음) |

- 여러 선언은 순서를 유지한 채 한 줄로 합칩니다 (`calc()`, `!important`, 따옴표 보존).
- 쉼표로 나열된 셀렉터는 규칙을 쪼개 호스트를 반복합니다 — `:style()`/`:remove()`가 마지막 셀렉터에만
  붙는 것을 막기 위해서입니다.
- `:has(a, b)`, `[data-x="a,b"]`, `:matches-css(/^[0-9]{2,3}/)` 처럼 괄호·중괄호 안의 쉼표/중괄호는
  건드리지 않습니다.

## 검증 결과 (adblock-rust 0.13.5, 실제 파싱)

| | 원본 uBO | 이 빌드 |
|---|---:|---:|
| 규칙 수 | 4,176 | 4,176 |
| 파싱 성공 | 3,736 (89.5%) | **4,004 (95.9%)** |
| 파싱 실패 | 440 (10.5%) | **172 (4.1%)** |
| 변환 규칙 중 거부 | — | **0** |

남은 172건은 도메인을 추측하지 않고는 일반 변환이 불가능한 규칙이라 **원문 그대로** 둡니다
(Brave는 이런 줄을 조용히 무시합니다):

| 건수 | 이유 |
|---:|---|
| 92 | 정규식 호스트네임 (`/site[0-9]+\.tv/##…`) — adblock-rust는 호스트네임에 정규식을 허용하지 않음 |
| 58 | `$domain=/정규식/` — 옵션 도메인도 정규식 불가 |
| 18 | 정규식 필터가 `$`로 끝나 옵션 구분자로 오인됨 |
| 2 | `$denyallow` 미구현 |
| 1 | `$header` 미구현 |
| 1 | `##^` HTML 필터링 미지원 |

즉 이 빌드는 원본의 **상위 집합**입니다: Brave가 이해하는 규칙은 전부 그대로 있고, 추가로 268건이
동작하게 됩니다. 원본에 없는 규칙을 만들어 넣지는 않습니다.

## 로컬 빌드

```bash
python3 scripts/build.py                 # jsDelivr에서 원본을 받아 dist/ 생성
python3 scripts/build.py --source-file ubo-chromium.txt   # 오프라인/특정 파일
python3 -m unittest discover -s tests -v                  # 변환기 단위 테스트
```

원본을 받지 못하면 npm 레지스트리 tarball로 자동 폴백합니다. 외부 의존성 없음(표준 라이브러리만).

### 엔진 검증 (선택, Rust 필요)

```bash
cd ci/brave_check
cargo run --release -- ../../dist/filterslists-KO-brave.txt 250
```

`brave_check`는 adblock-rust로 한 줄씩 파싱해 (1) 변환기가 만든 `:style(...)`/`:remove()` 규칙이 하나라도
거부되면, (2) 전체 거부 건수가 예산(기본 250)을 넘으면 exit 1로 실패합니다. CI에서도 같은 검사를
수행하므로, 원본 문법이 바뀌어 변환이 깨지면 빌드가 실패합니다.

## 저장소 구조

```
scripts/build.py          변환기 + 다운로더 (stdlib only)
tests/test_convert.py     변환 규칙 단위 테스트
ci/brave_check/           adblock-rust 기반 검증기 (Cargo)
dist/filterslists-KO-brave.txt   배포되는 리스트 (자동 생성, 직접 수정 금지)
.github/workflows/build.yml     6시간마다 빌드·검증·커밋
```

## 라이선스 및 출처

- 원본 필터 리스트: [FilteringDev/filterslists-KO](https://github.com/FilteringDev/filterslists-KO) — **GPL-3.0-only**
- 이 저장소의 변환 코드와 빌드 산출물도 동일하게 **GPL-3.0-only** 입니다 (`LICENSE` 참고).
- 상표·저작권은 각 원저작자에게 있으며, 이 저장소는 원본 프로젝트와 무관한 **비공식 포트**입니다.
- 원본 프로젝트는 AdGuard와 uBlock Origin만 공식 지원합니다. Brave에서의 동작은 이 저장소가 보증하지
  않으며, 원본 프로젝트에 Brave 관련 이슈를 올리는 것은 권장되지 않습니다.
