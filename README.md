# Game Audio Auto

게임용 효과음·환경음·대사·BGM을 만들고 편집·검수하는 Codex 스킬과 로컬 런타임입니다. 3D 프로젝트와 별도로 관리합니다.

공개 저장소에는 소스 코드·스킬·테스트만 포함됩니다. API 키, 개인 설정, 모델 가중치, 생성 음원, 카탈로그, 작업·청취 기록은 포함하지 않습니다. 키와 설정은 자신의 로컬 환경에서 구성합니다.

| 역할 | 구성 |
| --- | --- |
| 게임별 판단 | `game-audio` 스킬: 사운드 구성, 변주, 루프, 타이밍, 검수 |
| ElevenLabs 생성 | 선택한 모델을 지원하는 공식 플러그인 도구 우선. BGM은 Music v2.5를 사용하며, 플러그인이 미지원이면 저장된 키로 공식 API를 호출하는 런타임 사용 |
| 키가 없을 때 | 기본 `auto`가 로컬 전용으로 동작. 명시한 `only_local`은 키·플러그인이 있어도 유지 |
| 로컬 효과음 / 대사 | Stable Audio 3 / Qwen3-TTS를 필요한 시점에 개별 설치 |
| 선택형 캐릭터 대사 | 명시한 경우 Gemini 3.8 Flash TTS: 같은 voice ID로 상황별 연기 생성, 밀도 강화 후처리 기본 |
| BGM | ElevenLabs Music v2.5 기본. 로컬을 지정하거나 접근 수단이 없을 때 ACE-Step 1.5와 Stable Audio 3 중 요청에 맞춰 선택 |
| 공통 후처리 | 원본 보관, WAV 변환, 트림·게인·페이드·루프 편집, 대사 밀도 강화, 반복 청취 파일 |
| 기록 | 작업 ID, 원본/결과 해시, 제공자·모델, 편집 이력, 별도 청취·반복·통합 검수 |

플러그인 설치만으로 모든 생성 도구의 인증이 완료됐다고 가정하지 않습니다. 확인한 ElevenLabs 생성 스킬은 API 키를 요구합니다. 실제로 인증된 도구가 제공되면 별도 키를 다시 요구하지 않고 활용할 수 있습니다.

사용 안내는 [.agents/skills/game-audio/SKILL.md](.agents/skills/game-audio/SKILL.md), 정확한 명령과 예시는 [runtime.md](.agents/skills/game-audio/references/runtime.md)에 있습니다.

Codex에서 **`$game-audio 설명서`**라고 입력하면 기본 모델과 목소리·감정·로컬 모델·후처리·출력 옵션을 [간단 설명서](.agents/skills/game-audio/references/quick-manual.ko.md)로 안내합니다. 설명서 요청만으로 생성하거나 키를 조회하지 않습니다.

BGM 요청에서 `provider: "auto"`는 키가 있으면 ElevenLabs `music_v2_5`를 선택합니다. 확정한 `provider: "elevenlabs", model: "music_v2_5"`를 명시해도 됩니다. 현재처럼 플러그인이 v1/v2만 제공하는 경우 런타임이 `/v1/music`을 직접 호출합니다. [v2.5 요청 예시와 실행 명령](.agents/skills/game-audio/references/runtime.md#elevenlabs-bgm-v25)을 사용하면 됩니다. 명시한 로컬 모델·구버전은 유지합니다. 과거 로컬 선호 기록은 로컬 작업에 적용됩니다.

```powershell
uv sync --locked --python 3.12
uv run --no-sync python -m game_audio.cli doctor
uv run --no-sync python -m game_audio.cli plan .work/request.json
uv run --no-sync python -m game_audio.cli generate .work/request.json --async
```

FFmpeg가 필요합니다. 키는 `.secrets/elevenlabs_api_key`에 키 한 줄만 저장하거나 `ELEVENLABS_API_KEY` 환경변수로 제공합니다. 채팅·요청 JSON·Git에는 넣지 않습니다. `doctor --online`은 생성 없이 계정 상태를 확인합니다. 플러그인 결과는 `import`로 가져올 수 있습니다.

Gemini 대사는 **사용하라고 명시한 경우에만** 선택합니다. [Google AI Studio](https://aistudio.google.com/api-keys)에서 만든 키를 `.secrets/gemini_api_key`에 한 줄로 저장하면 됩니다. `GEMINI_API_KEY` / `GOOGLE_API_KEY` 또는 `GEMINI_API_KEY_FILE`도 지원합니다. `gemini-voices`로 생성 없이 접근을 확인하고, [캐릭터 음성 안내](.agents/skills/game-audio/references/character-voices.md)의 `voice-plan` → `voice-create` → `generate` 흐름으로 사용합니다. ElevenLabs 기본값은 유지하며 명시한 `only_local`은 Gemini도 차단합니다.

Gemini 대사는 `dialogue_processing: "auto"`가 **밀도 강화**를 적용합니다. 원본 생성 리비전은 보존하며, 작업의 `delivery_revisions`에 후처리 결과를 별도 기록합니다. `none`으로 끄거나, 기존 음원을 [finish-dialogue](.agents/skills/game-audio/references/runtime.md#dialogue-density-finishing)로 보정할 수 있습니다. ElevenLabs에는 자동으로 적용하지 않습니다. 다른 보정은 같은 원본에서 별도 비교하며, 실제 청취 승인과 파일 완성 상태는 구분합니다.

SSH/Linux에서 사용하려면 [설치 안내](.agents/skills/game-audio/references/execution-setup.ko.md)에 따라 **전체 런타임·스킬·FFmpeg**를 설치하고 해당 호스트의 비공개 키 파일을 설정합니다. 스킬 문서 복사만으로 서버 런타임이 갱신되지는 않습니다. Gemini·ElevenLabs API 사용에는 GPU나 로컬 생성 모델이 필요하지 않습니다.

캐릭터의 고정 음색과 대사별 감정 지시를 분리하고, voice ID·만료일·설계문·샘플 WAV·대사 WAV를 보관합니다. 현재 Google 사용자 정의 음성 ID는 1년 뒤 만료되며, 보관한 합성 WAV로 동일 ID/음색을 복원하는 기능은 보장되지 않습니다. 실제 사람 녹음과 동의를 요구하는 Voice Replication을 자동 갱신 수단으로 사용하지 않습니다. 일반 합성은 무료 할당량이 있지만 비공개 대본의 데이터 이용조건과 필요한 유료 API 결제는 해당 프로젝트에서 확인해야 합니다.

로컬 모델 설치는 [local-models.md](.agents/skills/game-audio/references/local-models.md)를 따릅니다. 기본 환경에는 모델과 가중치가 포함되지 않습니다. 플러그인/API 호출 성공, 로컬 추론 성공, 실제 청취 품질은 각각 확인해야 합니다. Eleven Music의 용도별 이용조건 기록은 생성과 별개로 보관하며, 근거가 없으면 미확인으로 남깁니다. 일반 생성·비교를 막지 않으며 실제 게임 출시 권한으로 자동 승인하지 않습니다.

## 테마파크 비교 플레이어

플레이어는 선택 기능이며, 기존에 생성한 로컬 음원과 카탈로그가 필요합니다. 새로 복제한 저장소에는 데모 음원·카탈로그가 없으므로 생성 CLI부터 사용하거나, 자신의 카탈로그를 `--catalog PATH`로 지정해 실행합니다.

`Open Audio Player.cmd`를 실행하면 저장된 음원을 바로 비교할 수 있습니다. 재생 중인 서버가 있으면 그대로 사용하며, 기본 주소는 `http://127.0.0.1:8767`입니다.

```powershell
powershell.exe -NoProfile -File scripts/open_comparison.ps1
# 브라우저를 열지 않고 서버만 시작 / 재사용
powershell.exe -NoProfile -File scripts/open_comparison.ps1 -NoOpen
```

BGM·군중·급강하·보스 BGM 탭, 생성된 후보 선택, 제공자별 재생, 순서대로 비교 재생, 반복, 볼륨 및 원본/비교 음량 전환을 제공합니다. `/?category=boss`로 보스 곡을 바로 열 수 있습니다. 다른 음원을 재생하면 기존 재생은 멈춥니다. 음량 조정은 별도 미리듣기 파일에만 적용합니다. 원본 WAV도 저장할 수 있습니다.

서버는 이 PC의 루프백 주소에서 명시한 카탈로그의 음원만 읽습니다. 키, 생성 API, 임의 경로 접근은 웹 화면에 노출하지 않습니다. 카탈로그는 `.assets/deliveries/themepark-comparison-20260915/catalog.json`이며, 완료된 생성·가져오기 작업은 `scripts/add_comparison_job.py JOB_ID bgm|crowd|drop|boss`로 검증·추가합니다. 개별 가져오기 작업은 `--candidate-start B`처럼 후보 위치를 지정할 수 있습니다. 기존 위치에 다른 작업을 덮어쓰지 않습니다. 새 음원은 재생을 방해하지 않는 시점에 자동 반영됩니다. 다른 카탈로그는 `scripts/serve_comparison.py --catalog PATH --port PORT`로 열 수 있습니다.

Hugging Face 인증은 기존 토큰 파일 경로를 `audio-system.local.json`의 `huggingface_token_file`에 설정하거나 `HF_TOKEN`으로 제공합니다. 토큰이 유효해도 모델별 접근 동의는 해당 계정에서 완료해야 합니다. 구형 uv가 `#`이 포함된 경로를 처리하지 못하면 `bootstrap_local.py --backend-root`로 모델 환경만 별도 경로에 설치할 수 있습니다.

검증:

```powershell
uv run --no-sync ruff check src scripts tests .agents/skills/game-audio/scripts
uv run --no-sync pytest -q
```

테스트는 합성 오디오 파일·모의 API를 사용하며 유료 요청을 보내지 않습니다. 실제 Windows 백그라운드 편집 작업도 검사합니다. 이 테스트 결과는 모델의 자연스러운 음질을 입증하지 않습니다.
