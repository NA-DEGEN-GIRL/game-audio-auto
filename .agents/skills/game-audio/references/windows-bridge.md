# Windows 브리지 라우팅

**한국어** | [English](windows-bridge.en.md)

비Windows 호스트에서 이 스킬의 래퍼를 실행하기 전, 또는 래퍼가 런타임을 고르는 방식을 바꾸기 전에 읽는다.

## 래퍼가 라우팅하는 이유

`scripts/audioctl.py`는 기본적으로 같은 머신의 연결된 런타임 체크아웃을 실행한다. 자신보다 네 단계 위의 체크아웃을 찾아 `<root>/.venv/bin/python -m game_audio.cli --root <root>`를 실행한다(Windows에서는 `.venv/Scripts/python.exe`). 설치된 환경, 즉 Python 환경과 FFmpeg, 격리된 로컬 모델 환경(ACE-Step·Stable Audio·Qwen), 개인 키와 HF 토큰, GPU 잠금은 모두 그 체크아웃과 그 설정에 남는다. 스킬 폴더만 다른 프로젝트로 복사하면 지침은 따라오지만 그 환경은 따라오지 않는다. 네이티브 Linux 런타임은 래퍼가 그대로 지원하며(`<root>/.venv/bin/python`), 복사가 아니라 자체 `uv sync`와 FFmpeg·백엔드 설치가 필요하다.

Windows 머신에 이미 동작하는 체크아웃이 있다면, 등록된 브리지로 같은 명령을 그쪽에서 실행할 수 있다.

## 래퍼가 위임하는 조건

다음을 모두 만족해야 위임한다.

- `--execution windows`를 명시했거나, `auto`이면서 네이티브 런타임 등록이 없음. [실행 위치·설치 안내](execution-setup.ko.md)를 따른다.
- 호스트가 Windows가 아님(`os.name != "nt"`). Windows는 항상 로컬 런타임을 쓴다
- 디스크립터 파일이 존재하고, 같은 사용자 소유의 비공개 파일이며, JSON 객체로 파싱됨
- 그 `enabled_skills` 목록에 `game-audio`가 포함됨
- 디스크립터가 가리키는 클라이언트가 디스크립터와 같은 폴더의 형제 파일이고, 심볼릭 링크가 아닌 비공개 파일로 존재함

디스크립터 탐색 순서:

1. `$CODEX_WORKSPACE_SKILL_BRIDGE` — `connection.json`의 명시적 경로. 존재하지 않으면 설정 오류다.
2. `$CODEX_HOME/workspace-skill-bridge/connection.json`
3. `~/.codex/workspace-skill-bridge/connection.json` — `CODEX_HOME`이 관리 프로필을 가리킬 때의 원래 사용자 프로필

래퍼가 읽는 필드는 `client`와 `enabled_skills`뿐이다. `client`는 생략할 수 있으며, 그때는 디스크립터 옆의 `client.py`를 기대한다. 디스크립터는 설치 프로그램이 원격 계정에 만드는 연결의 원격 쪽이며 범위 한정 bearer 자격 증명을 담으므로, 그곳에서 모드 600을 유지한다.

Windows 경로를 선택했을 때의 설정 오류는 파일과 수정 방법을 밝히며 실행을 멈춘다. 로컬 설치 안내로 조용히 내려가지 않는다. 명시적인 local 실행이나 네이티브 런타임이 등록된 auto는 브리지가 없어도 실행할 수 있다.

- 존재하지 않는 파일을 가리키는 명시적 재정의
- 읽을 수 없거나, 유효한 JSON이 아니거나, JSON 객체가 아닌 디스크립터
- 이 스킬을 활성화했지만 비공개(모드 600)·같은 사용자 소유·비심볼릭 파일이 아닌 디스크립터
- 없거나, 상대 경로이거나, 디스크립터 폴더 밖이거나, 심볼릭 링크이거나, 비공개·같은 사용자 소유가 아닌 클라이언트

디스크립터가 정상적으로 파싱되지만 이 스킬을 나열하지 않으면 오류가 아니다. 래퍼는 로컬 런타임을 실행한다. 하나의 디스크립터가 여러 스킬을 담당하는 방식이기 때문이다. 설치 프로그램이 원격의 네이티브 `~/.codex/skills/game-audio` 설치를 보존할 때도 같은 방식으로 이 스킬이 목록에서 빠진다. 디스크립터가 아예 없을 때도 로컬 동작을 그대로 유지한다. Linux에서는 `<root>/.venv/bin/python -m game_audio.cli --root <root>`이며, 자체 `uv sync`와 FFmpeg·백엔드 설치가 필요하다. 클라이언트 자체가 실패하면 그 메시지와 종료 코드를 그대로 돌려준다.

## 브리지 클라이언트 프로토콜

설치 프로그램은 활성화된 스킬을 `~/.agents/skills/<name>`에 프로젝션하고, 원격 계정의 `~/.codex/workspace-skill-bridge/`에 `connection.json`과 나란히 클라이언트를 쓰며 두 브리지 파일 모두 모드 600으로 둔다. 이 저장소는 클라이언트를 포함하지 않는다. 클라이언트는 SSH로 전달된 인증 루프백 엔드포인트로 Windows 작업자와 통신하므로 포워드가 살아 있어야 한다.

```sh
python3 <client> [--connection <connection.json>] catalog
python3 <client> --connection <connection.json> read game-audio skill:/SKILL.md
python3 <client> --connection <connection.json> read game-audio skill:/references/runtime.md
python3 <client> --connection <connection.json> upload <local-path>
python3 <client> --connection <connection.json> run game-audio --request-id <uuid> --wait 30 -- <command> [args...]
python3 <client> --connection <connection.json> job <bridge-job-id>
python3 <client> --connection <connection.json> fetch game-audio runtime:/.assets/audio/<name>/<revision>/take-001/master.wav <new-local-file>
```

- `catalog`는 등록된 스킬과 그 Windows 런타임 루트를 나열한다.
- `read`는 문서만 제공한다. `skill:/SKILL.md`, `skill:/references/<name>.md`, `runtime:/docs/<name>.md`가 전부이며 나머지 경로는 거부된다. 오디오 참조 문서는 스킬 폴더에 있으므로 `skill:`로 읽는다. 로그나 키, 프로젝트 파일은 노출되지 않는다.
- `upload`는 로컬 파일을 1 MiB 청크로 올리고 업로드 레코드를 출력한다. 레코드의 `path`가 요청에 쓸 Windows 경로다. 업로드 중에는 파일이 바뀌면 안 된다.
- `run`은 `--` 뒤에 스킬 명령을 요구하며 브리지 옵션은 그 앞에 온다. `--wait`는 기본 30초, 최대 300초다. 작업자는 이 래퍼의 명령만 허용하고 `--root`와 `_run` 같은 워커 진입점은 거부한다. `mode`·`key-status` 같은 설정 명령도 노출되지 않으므로 provider 정책은 Windows 호스트에서 바꾼다. 요청 ID를 기록하며 같은 ID의 동일 재시도에는 같은 작업을 돌려준다.
- `job`은 `queued`, `running` 또는 종료 상태 `complete`/`failed`/`interrupted`를 `exit_code`, `error`, 잘린 `stdout`/`stderr`와 함께 보고한다.
- `fetch`는 산출물 하나를 가져오며 작업자의 `stat`과 SHA-256을 검증한다. 이 세션에서 올린 파일은 `upload:/<upload-id>/<name>`, 런타임 산출물은 `runtime:/.assets/...` 또는 `runtime:/.work/...`, 또는 그 디렉터리 안의 절대 경로를 쓴다. 목적지 파일이 이미 있으면 안 된다.

## 경로 규칙

래퍼는 인자를 그대로 전달하며 경로를 변환하지 않는다. 순서가 중요하다.

1. 의존 파일을 먼저 업로드한다. `edit`·`import`용 원본 오디오, 참조 오디오, 요청이 가리키는 파일들이며, 작업자가 돌려준 Windows 경로를 기억한다.
2. 로컬의 요청 JSON 사본에서 경로를 그 Windows 경로로 직접 고친다. 브리지는 JSON을 대신 고쳐 주지 않는다. 상대 경로는 Windows 런타임 루트 기준으로 해석된다.
3. 고친 최종 JSON을 업로드하고, 돌려받은 Windows 경로를 `run`에 넘긴다.
4. 출력은 Windows 경로로 지정하고(런타임은 자체 `.assets/`·`.work/` 아래에 쓴다), `runtime:` 또는 `upload:` 경로로 가져온다.

## 두 개의 작업 계층

브리지 job ID와 런타임 자체의 job ID는 서로 다른 객체다.

- `run`은 브리지 job ID를 돌려준다. 클라이언트는 `--wait`까지 폴링하고, `complete`면 작업의 `stdout`/`stderr`를 출력하며 스킬의 종료 코드를 반환한다. `failed`/`interrupted`면 작업 레코드를 출력하고 1로 끝난다.
- 클라이언트는 작업자에게 연락하기 전에 브리지 디렉터리의 `requests/<request-id>.json`에 요청을 기록하고 stderr에 `Skill bridge request: <id>`를 출력한다. 작업자는 같은 ID의 동일 재시도에 같은 작업을 돌려주고, 같은 ID의 다른 명령은 거부한다.
- 런타임은 리비전 폴더에 별도의 작업 레코드를 남긴다. CLI(`generate ... --async`)가 출력하는 런타임 job ID를 같은 경로로 `job <runtime-job-id>`에 넣어 조회한다.

필요한 상태에 맞는 작업을 조회하고, 작업이 진행 중이거나 결과가 불확실할 때 대체 제출을 하지 않는다. 결제가 걸린 ElevenLabs 제출의 결과가 불확실하면 저장된 영수증과 `resume`, `recover-history`로 정합성을 맞추고, 같은 요청을 다시 보내지 않는다. 브리지 연결이 끊긴 것은 제출 실패의 증거가 아니다.

## 예시: Linux 게임 프로젝트에서 효과음 생성

```sh
CLIENT="${CLIENT:-$HOME/.codex/workspace-skill-bridge/client.py}"   # 원격의 설치 기본 경로

python3 "$CLIENT" catalog

# 1. 의존 파일을 먼저 올리고 돌려받은 Windows 경로를 기억한다.
python3 "$CLIENT" upload ./source/door-hinge.wav

# 2. .work/door.json의 경로를 그 값으로 고친 뒤 최종 JSON을 올린다.
python3 "$CLIENT" upload .work/door.json

# 3. 실행한다. 브리지 옵션은 -- 앞에 온다.
python3 "$CLIENT" run game-audio --request-id "$REQUEST_ID" --wait 30 -- generate <request> --async
python3 "$CLIENT" job "$BRIDGE_JOB_ID"
# 이어서 CLI가 출력한 런타임 job ID를 조회하면 take 경로와 리비전 폴더가 나온다.

# 4. 산출물과 사이드카를 가져온다.
python3 "$CLIENT" fetch game-audio runtime:/.assets/audio/door/<revision>/take-001/master.wav ./audio/door.wav
python3 "$CLIENT" fetch game-audio runtime:/.assets/audio/door/<revision>/take-001/analysis.json ./audio/door.analysis.json
python3 "$CLIENT" fetch game-audio runtime:/.assets/audio/door/<revision>/manifest.json ./audio/door.manifest.json
```

`--connection`을 생략하면 클라이언트가 자체 탐색을 쓴다. `$CODEX_WORKSPACE_SKILL_BRIDGE`, `$CODEX_HOME/workspace-skill-bridge/connection.json`, `~/.codex/workspace-skill-bridge/connection.json` 순서다. 디스크립터가 다른 곳에 있을 때만 `--connection <path>`를 명시한다.

## 가져온 뒤의 검토

판단하기 전에 산출물과 사이드카를 함께 가져온다. 테이크 WAV와 `analysis.json`, `review.json`, 리비전 `manifest.json`이 기본이고, 원본 코덱 파일이 필요하면 제공자 영수증과 함께 받는다. `fetch`가 SHA-256을 검증하므로 해시에 묶인 검사와 `review` 기록은 로컬 사본에도 그대로 적용된다.

가져온 WAV를 다시 인코딩하거나 편집한 뒤 원래 검토를 주장하지 않는다. 청취 증거는 실제로 들은 사람이나 오디오 청취 도구만 만들 수 있고, 수치 분석은 청취가 아니다. 들을 수 없으면 `listening: unreviewed`로 남기고 재생 가능한 미리보기를 전달한다.

## Windows 호스트에 남는 것

- 런타임 체크아웃, 그 Python 환경, FFmpeg, 격리된 로컬 모델 환경과 가중치
- provider 자격 증명(ElevenLabs 키, Hugging Face 토큰)은 이 호스트에 남고 업로드되지 않는다. 전송 디스크립터는 의도된 예외로, 설치 프로그램이 원격 계정에 만들므로 그곳에서 모드 600을 유지하고 요청·로그·대화로 복사하지 않는다
- GPU와 그 잠금: 로컬 추론은 3D 런타임과 같은 잠금 파일을 공유할 수 있으므로 브리지가 병렬 루트를 만들면 안 된다

## 이 경로가 바꾸지 않는 것

- provider 규칙: 키가 있으면 ElevenLabs가 기본이고, `only_local`은 모든 원격 생성을 막는다. Music v2.5 기본과 크레딧 한도, `max_credits` 차단 규칙도 그대로다.
- 작업·복구 규칙: 중복 제출이나 자동 유료 재시도는 없고, 불확실한 결과는 정합성 확인으로 처리한다.
- 증거 규칙: 수치 분석, 청취, 반복 재생, 게임 통합은 각각 별개다. `review` 사이드카는 전달된 파일 해시에 묶인다.

## 검증된 전송 증거 (2026-09-20)

2026-09-20에 실제 Windows 작업자 + SSH 루프백 전송을 살아 있는 픽스처 세션에서 끝까지 확인했다. 사용자 프로젝트가 아니다.

- 원격의 프로젝션된 래퍼가 Windows 런타임으로 위임해 이 체크아웃의 `doctor` 출력을 돌려주었다
- WAV 입력을 업로드해 런타임 `import`로 처리하고, 결과 WAV와 `manifest.json`을 SHA-256 검증과 함께 가져왔다
- 생성, 결제 API, 로컬 모델 추론은 실행하지 않았고 청취 검토도 하지 않았다

생성 품질, 청취 증거, 로컬 백엔드 추론은 이 전송으로 아직 검증되지 않았다.

## 유지보수 계약

- 래퍼는 얇게 유지한다. 디스크립터 탐색·검증과 인자 전달만 담당하고, 경로 변환·요청 재작성·request ID 생성·provider 로직·비밀 처리는 넣지 않는다.
- CLI 명령이 늘어도 인자를 그대로 전달하므로 래퍼는 바꿀 필요가 없다. 다만 작업자의 스킬별 허용 명령 목록에 새 명령을 넣지 않으면 `run`이 거부한다.
- Windows 판정은 런타임을 소유한 호스트에서 로컬 경로가 우선하게 하고, 클라이언트가 같은 래퍼를 원격에서 실행할 때의 재귀를 막는다.
- 클라이언트 프로토콜이 바뀌면 이 문서의 두 언어판과 래퍼를 함께 고치고, 디스크립터의 `client`·`enabled_skills` 키는 안정적으로 유지한다.
- `tests/test_skill_bridge_routing.py`가 탐색 순서, 설정 오류, 파일 신뢰 검사(소유자·모드·심볼릭·형제 경로), 스킬 활성화 조건, Windows 우회, 대체 없는 오류를 mocked subprocess, 주입된 플랫폼·환경, mocked POSIX 메타데이터로 고정한다.
