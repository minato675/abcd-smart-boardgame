# QnA Server

보드게임 규칙 설명 QnA 모듈입니다. Spring 서버가 MQTT로 보내는
`/room/{roomNumber}/qna/start`를 받아 준비 상태와 답변 결과를 다시 MQTT로 발행합니다.

현재 버전은 명세의 QnA 절차를 끝까지 실행합니다. 기본 실행 경로는 GMS
(Gen AI Management System)의 Gemini audio 입력에 질문 음성과 룰북 context를 함께 보내
질문 인식과 답변 생성을 한 번에 처리합니다.
`--self-test`만 API 키 없이 MQTT payload 모양을 확인하는 오프라인 테스트입니다.

- MQTT `qna/start` 수신
- `QNA_MIC_START_DELAY_SECONDS`만큼 내부 안정화 대기
- MQTT `qna/ready` 발행
- `qna/ready` 발행 직후 로컬 효과음 재생
- 효과음 직후 마이크 녹음 시작
- 마이크 녹음 종료
- MQTT `qna/thinking` 발행
- 녹음 오디오를 압축하고 `boardGameName`에 해당하는 룰북 context와 함께 Gemini에 전달
- Gemini가 `req` 질문 텍스트와 `res` 답변 텍스트를 JSON으로 생성
- Jetson 터미널에 인식된 질문을 확인용 박스로 출력
- MQTT `qna/res` 발행
- GMS 또는 ElevenLabs TTS로 답변 음성 생성 및 재생
- MQTT `wake/start-listen` 발행

## 토픽

| Topic | 방향 | 설명 |
| --- | --- | --- |
| `/room/{roomNumber}/qna/start` | Spring -> qna-server | QnA 시작 명령 |
| `/room/{roomNumber}/qna/ready` | qna-server -> Spring | QnA 서버 준비 완료 |
| `/room/{roomNumber}/qna/thinking` | qna-server -> Spring | 음성 인식/녹음 종료 후 답변 생성 시작 |
| `/room/{roomNumber}/qna/res` | qna-server -> Spring | 인식 질문과 답변 결과 |
| `/room/{roomNumber}/wake/start-listen` | qna-server -> wake | QnA 종료 후 Wake Word 재활성화 |

## 페이로드

`qna/start`:

```json
{
  "transactionId": "123e4567-e89b-12d3-a456-556642440000",
  "boardgameName": "루미큐브",
  "players": 4
}
```

`qna/ready`:

```json
{
  "transactionId": "123e4567-e89b-12d3-a456-556642440000",
  "status": "ready"
}
```

`qna/thinking`:

```json
{}
```

`qna/res`:

```json
{
  "transactionId": "123e4567-e89b-12d3-a456-556642440000",
  "req": "여기에서 12 붙일 수 있어?",
  "res": "연속 묶음은 같은 색의 연속된 숫자 3개 이상이어야 해요..."
}
```

## 실행

```powershell
cd table\qna-server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH=".\src"
$env:GMS_BASE_URL="https://gms.ssafy.io/gmsapi/api.openai.com"
$env:GMS_API_KEY="발급받은_GMS_API_KEY"
$env:GMS_GEMINI_AUDIO_BASE_URL="https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com"
$env:GMS_GEMINI_AUDIO_REQUEST_STYLE="generate-content"
$env:GMS_GEMINI_AUDIO_MODEL="gemini-2.5-flash"
$env:GMS_TTS_MODEL="gpt-4o-mini-tts"
python -m qna_server
```

기본 MQTT 설정은 `inte-server/src/main/resources/application.properties`와 맞춰져 있습니다.

| 환경 변수 | 기본값 |
| --- | --- |
| `MQTT_HOST` | `i15a402.p.ssafy.io` |
| `MQTT_PORT` | `8113` |
| `MQTT_USERNAME` | `ssafy` |
| `MQTT_PASSWORD` | `ssafy` |
| `MQTT_QOS` | `1` |
| `QNA_RULE_DIR` | `table/qna-server/rules` |
| `QNA_PUBLISH_WAKE_START` | `true` |
| `GMS_BASE_URL` | 필수. OpenAI 계열 모델 사용 시 `https://gms.ssafy.io/gmsapi/api.openai.com` |
| `GMS_API_KEY` | 필수 |
| `GMS_AUTH_HEADER` | `Authorization` |
| `GMS_AUTH_SCHEME` | `Bearer` |
| `GMS_TTS_ENDPOINT` | `/v1/audio/speech` |
| `GMS_EMBEDDING_ENDPOINT` | `/v1/embeddings` |
| `GMS_MODELS_ENDPOINT` | `/v1/models` |
| `GMS_GEMINI_AUDIO_BASE_URL` | `https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com` |
| `GMS_GEMINI_AUDIO_ENDPOINT` | 빈 값. `generate-content` 기본 경로 사용 |
| `GMS_GEMINI_AUDIO_REQUEST_STYLE` | `generate-content` |
| `GMS_GEMINI_AUDIO_MODEL` | `gemini-2.5-flash` |
| `GMS_TTS_MODEL` | `gpt-4o-mini-tts` |
| `GMS_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `GMS_TTS_VOICE` | `alloy` |
| `GMS_TTS_RESPONSE_FORMAT` | `wav` |
| `ELEVENLABS_API_KEY` | 빈 값. `QNA_TTS_MODE=elevenlabs`일 때 필수 |
| `ELEVENLABS_BASE_URL` | `https://api.elevenlabs.io` |
| `ELEVENLABS_VOICE_ID` | `JBFqnCBsd6RMkjVDRZzb` |
| `ELEVENLABS_MODEL_ID` | `eleven_flash_v2_5` |
| `ELEVENLABS_OUTPUT_FORMAT` | `pcm_24000` |
| `ELEVENLABS_STABILITY` | `0.45` |
| `ELEVENLABS_SIMILARITY_BOOST` | `0.8` |
| `ELEVENLABS_STYLE` | `0.0` |
| `ELEVENLABS_USE_SPEAKER_BOOST` | `true` |
| `ELEVENLABS_TIMEOUT_SECONDS` | `30.0` |
| `QNA_VECTOR_BACKEND` | `local` |
| `QNA_RETRIEVAL_MODE` | `hybrid` |
| `QNA_VECTOR_INDEX_PATH` | `table/qna-server/var/vector-index.json` |
| `QDRANT_URL` | 빈 값. `QNA_VECTOR_BACKEND=qdrant`일 때 필수 |
| `QDRANT_API_KEY` | 빈 값 |
| `QDRANT_COLLECTION` | `boardgame_rules` |
| `QDRANT_TIMEOUT_SECONDS` | `30.0` |
| `QNA_MIC_START_DELAY_SECONDS` | `0.5` |
| `QNA_RECORD_SECONDS` | `4.0` |
| `QNA_RECORD_MIN_SECONDS` | `2.0` |
| `QNA_RECORD_SAMPLE_RATE` | `16000` |
| `QNA_RECORD_CHANNELS` | `1` |
| `QNA_INPUT_DEVICE` | 빈 값. sounddevice 기본 입력 장치 |
| `QNA_RECORD_SILENCE_SECONDS` | `0.8` |
| `QNA_RECORD_SILENCE_THRESHOLD` | `500` |
| `QNA_RECORD_NOISE_SECONDS` | `0.35` |
| `QNA_RECORD_THRESHOLD_MULTIPLIER` | `2.5` |
| `QNA_TTS_MODE` | `gms` |
| `QNA_TTS_OUTPUT_DIR` | `table/qna-server/var/audio` |
| `QNA_TTS_PLAY_AUDIO` | `true` |
| `QNA_TTS_STREAMING` | `false` |
| `QNA_READY_SOUND_ENABLED` | `true` |
| `QNA_READY_SOUND_FREQUENCY` | `880` |
| `QNA_READY_SOUND_DURATION_SECONDS` | `0.18` |
| `QNA_READY_SOUND_VOLUME` | `0.22` |
| `QNA_READY_SOUND_OUTPUT_DEVICE` | 빈 값. sounddevice 기본 출력 장치 |

`GENAI_API_KEY` 또는 `GEN_AI_API_KEY`도 키 이름으로 받을 수 있지만, 팀 공유 문서에는
`GMS_API_KEY`를 표준으로 쓰는 것을 권장합니다.

## 선택 모델

현재 QnA 기본 모델은 GMS 모델 목록 기준으로 다음 조합을 사용합니다.

| 용도 | 모델 | 선택 이유 |
| --- | --- | --- |
| 질문 인식 + 답변 생성 | `gemini-2.5-flash` | 음성 파일과 룰북 context를 한 번에 넣어 `req/res`를 바로 생성 |
| TTS | `gpt-4o-mini-tts` 또는 ElevenLabs `eleven_flash_v2_5` | 기본은 GMS TTS, 자연스러운 목소리가 필요하면 ElevenLabs 사용 |
| Embedding | `text-embedding-3-small` | Qdrant/VectorDB 인덱스 확인용. direct 실행 경로에서는 검색에 사용하지 않음 |

GMS 화면에는 `gemini 2.5 flash`, `gpt 4o mini`처럼 공백이 있는 표시명으로 보일 수 있지만,
API 요청의 `model` 값은 `gemini-2.5-flash`, `gpt-4o-mini-tts`처럼
하이픈이 들어간 값을 사용합니다.

## GMS API 계약

현재 QnA 답변 경로는 Gemini `generateContent` 형태의 GMS 게이트웨이를 사용합니다.
GMS TTS와 모델 목록 확인, VectorDB 인덱스 확인 명령은 OpenAI-compatible 형태의 GMS
게이트웨이를 함께 사용합니다.

- Direct answer: `POST {GMS_GEMINI_AUDIO_BASE_URL}/v1beta/models/{GMS_GEMINI_AUDIO_MODEL}:generateContent`
- TTS: `POST {GMS_BASE_URL}{GMS_TTS_ENDPOINT}` text to wav 또는 ElevenLabs TTS
- Embedding: `POST {GMS_BASE_URL}{GMS_EMBEDDING_ENDPOINT}` text to vector

팀 GMS의 path가 다르면 `GMS_*_ENDPOINT` 값만 바꿉니다. 요청/응답 형식 자체가 다르면
`src/qna_server/gms_client.py`의 Gemini audio direct 요청 메서드만 맞추면 QnA 전체 흐름은 그대로 유지됩니다.
인증이 `x-api-key: KEY` 형태라면 `GMS_AUTH_HEADER=x-api-key`, `GMS_AUTH_SCHEME=`처럼
설정하면 됩니다.

GMS가 OpenAI-compatible 모델 목록 API를 제공하면 다음 명령으로 사용 가능한 모델 ID를
확인할 수 있습니다.

```powershell
$env:PYTHONPATH=".\src"
$env:GMS_BASE_URL="https://gms.ssafy.io/gmsapi/api.openai.com"
$env:GMS_API_KEY="발급받은_GMS_API_KEY"
python -m qna_server --list-gms-models
```

## Gemini Audio Direct

QnA 서버는 Gemini audio direct 방식으로 동작합니다.

```bash
export GMS_GEMINI_AUDIO_BASE_URL=https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com
export GMS_GEMINI_AUDIO_ENDPOINT=
export GMS_GEMINI_AUDIO_REQUEST_STYLE=generate-content
export GMS_GEMINI_AUDIO_MODEL=gemini-2.5-flash
```

실행 순서는 다음과 같습니다.

```text
마이크 녹음 -> qna/thinking {} 발행 -> 오디오 압축 -> 오디오 + 해당 게임 룰북 전체 context를 Gemini로 전송
-> Gemini가 {"question": "...", "answer": "..."} JSON 생성
-> qna/res req/res 발행 -> answer TTS
```

이 방식에서는 `QNA_STT_MODE`의 전사 결과를 사용하지 않습니다. 다만 마이크 녹음 설정
(`QNA_INPUT_DEVICE`, `QNA_RECORD_CHANNELS`, `QNA_RECORD_SAMPLE_RATE`)은 그대로 사용합니다.
질문 텍스트가 아직 없으므로 VectorDB 검색 대신 `boardGameName`에 해당하는 룰북 chunk 전체를
Gemini context로 전달합니다.

## RAG / VectorDB

현재 Gemini direct 실행 경로에서는 VectorDB 검색을 사용하지 않습니다.
질문 텍스트가 나오기 전 단계에서 오디오와 룰북을 함께 Gemini에 보내기 때문에,
`boardGameName`에 해당하는 룰북 chunk 전체가 context로 들어갑니다.

Qdrant/VectorDB 코드는 인덱스 구축 확인과 향후 검색형 RAG 복귀를 위해 유지합니다.

로컬 개발 기본값은 `QNA_VECTOR_BACKEND=local`입니다.

- 서버 시작 시 `rules/*.md`를 chunk로 나눈다.
- `GMS_EMBEDDING_MODEL=text-embedding-3-small`로 chunk embedding을 생성한다.
- 생성한 embedding은 `QNA_VECTOR_INDEX_PATH`의 JSON 파일에 저장한다.
- 룰북 내용이나 embedding 모델이 바뀌면 인덱스를 자동으로 다시 만든다.
- `--build-vector-index` 명령으로 Qdrant collection과 embedding 저장 상태를 확인할 수 있다.

EC2 배포에서 외부 VectorDB 서버를 사용할 때는 `QNA_VECTOR_BACKEND=qdrant`를 사용합니다.
Qdrant는 Docker 컨테이너 하나로 EC2에 올릴 수 있고, qna-server는 REST API로 collection 생성,
point upsert, vector search를 수행합니다.

EC2에서 Qdrant 예시:

```bash
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -v /opt/qdrant/storage:/qdrant/storage \
  qdrant/qdrant
```

qna-server 환경변수:

```powershell
$env:QNA_VECTOR_BACKEND="qdrant"
$env:QNA_RETRIEVAL_MODE="hybrid"
$env:QDRANT_URL="http://EC2_HOST_OR_PRIVATE_IP:6333"
$env:QDRANT_COLLECTION="boardgame_rules"
$env:GMS_EMBEDDING_MODEL="text-embedding-3-small"
```

Qdrant에 API key를 걸었다면 다음 값도 설정합니다.

```powershell
$env:QDRANT_API_KEY="발급받은_QDRANT_API_KEY"
```

인덱스만 먼저 만들거나 확인하려면 다음 명령을 실행합니다.

```powershell
$env:PYTHONPATH=".\src"
$env:GMS_BASE_URL="https://gms.ssafy.io/gmsapi/api.openai.com"
$env:GMS_API_KEY="발급받은_GMS_API_KEY"
$env:GMS_EMBEDDING_MODEL="text-embedding-3-small"
python -m qna_server --build-vector-index
```

`QNA_RETRIEVAL_MODE` 값:

- `hybrid`: 기본값. VectorDB 검색과 키워드 검색을 합친다.
- `vector`: VectorDB 검색을 우선 사용하고 실패 시 에러를 낸다.
- `keyword`: 기존 키워드 검색만 사용한다.

`QNA_VECTOR_BACKEND` 값:

- `local`: 로컬 JSON 파일 기반 VectorDB. 개발/단독 실행용.
- `qdrant`: 외부 Qdrant 서버 기반 VectorDB. EC2 최종 배포용.

## TTS Streaming

QnA 답변 생성은 Gemini direct 단일 응답으로 처리합니다. 답변 텍스트가 준비되면
`qna/res`를 발행하고, TTS는 별도 작업 큐에서 재생합니다.

TTS HTTP streaming도 켤 수 있습니다. 이 모드에서는 `pcm` chunk를 받는 즉시
스피커로 출력하므로 wav 파일 생성 완료를 기다리지 않습니다.

```powershell
$env:QNA_TTS_STREAMING="true"
$env:GMS_TTS_RESPONSE_FORMAT="pcm"
python -m qna_server
```

`GMS_TTS_RESPONSE_FORMAT=pcm`이면 수신한 PCM chunk를 바로 스피커로 출력합니다.
단, GMS 서버가 응답을 내부에서 버퍼링해 한 번에 내려주면 클라이언트는 그보다 먼저
재생할 수 없으므로 `python -m qna_server --check-tts-streaming`으로 실제 chunk 응답을 확인합니다.
GMS가 `pcm`을 지원하지 않으면 `wav`로 되돌립니다.

`generativelanguage.googleapis.com` 도메인으로 보낼 때는 GMS 키를 Google/Gemini 방식인
`x-goog-api-key` 헤더로 전송합니다. OpenAI-compatible 경로는 기존처럼 `Authorization: Bearer`를 사용합니다.
GMS proxy는 큰 raw WAV inline 요청에서 `contents is not specified` 같은 잘못된 400을 반환할 수 있으므로,
qna-server는 Gemini에 보낼 때 녹음 wav를 `ffmpeg`로 16kHz mono OGG Vorbis로 압축한 뒤
`inline_data`에 넣습니다.

Jetson에 `ffmpeg`가 없으면 먼저 설치합니다.

```bash
sudo apt-get install -y ffmpeg
```

GMS의 Gemini 모델 상세 화면에 `interactions` 형태의 URL이 표시되면 다음처럼 바꿉니다.

```bash
export GMS_GEMINI_AUDIO_REQUEST_STYLE=interactions
export GMS_GEMINI_AUDIO_ENDPOINT=/v1beta/interactions
```

GMS가 Gemini 모델도 OpenAI-compatible chat completion으로만 열어두었다면 다음처럼 바꿉니다.

```bash
export GMS_GEMINI_AUDIO_REQUEST_STYLE=openai-chat
export GMS_GEMINI_AUDIO_BASE_URL=https://gms.ssafy.io/gmsapi/api.openai.com
export GMS_GEMINI_AUDIO_ENDPOINT=/v1/chat/completions
```

TTS:

- `QNA_TTS_MODE=gms`: 기본값. GMS TTS로 wav를 만들고 `QNA_TTS_OUTPUT_DIR`에 저장한다.
- `QNA_TTS_MODE=elevenlabs`: ElevenLabs TTS streaming API를 사용한다. 기본 모델은 저지연 다국어 모델 `eleven_flash_v2_5`이고, 기본 출력은 실시간 재생용 `pcm_24000`이다.
- `QNA_TTS_MODE=windows`: 임시 확인용. GMS TTS 대신 Windows `System.Speech`를 사용한다.

ElevenLabs로 TTS를 바꾸려면 다음 값을 설정합니다. STT, LLM, Embedding은 그대로 GMS를 사용하고,
답변 음성 합성만 ElevenLabs로 교체됩니다.

```bash
export QNA_TTS_MODE=elevenlabs
export QNA_TTS_STREAMING=true
export ELEVENLABS_API_KEY="발급받은_ELEVENLABS_API_KEY"
export ELEVENLABS_VOICE_ID="사용할_VOICE_ID"
export ELEVENLABS_MODEL_ID=eleven_flash_v2_5
export ELEVENLABS_OUTPUT_FORMAT=pcm_24000
```

Jetson에서 USB/캡처보드 마이크를 직접 지정하려면 먼저 장치 목록을 확인합니다.

```bash
python - <<'PY'
import sounddevice as sd
print(sd.query_devices())
PY
```

예를 들어 Sony 카메라/캡처보드 마이크가 `24 MS2109: USB Audio (hw:2,0)`처럼
48kHz stereo 장치로 잡히면 다음처럼 실행합니다. qna-server는 stereo 입력을 STT용
mono wav로 변환한 뒤, 룰북 context와 함께 Gemini audio direct 요청에 전달합니다.

```bash
export QNA_INPUT_DEVICE=24
export QNA_RECORD_CHANNELS=2
export QNA_RECORD_SAMPLE_RATE=48000
export QNA_MIC_START_DELAY_SECONDS=0.5
export QNA_READY_SOUND_ENABLED=true
python -m qna_server
```

qna-server는 `QNA_MIC_START_DELAY_SECONDS`만큼 먼저 내부 안정화 대기를 마친 뒤
`qna/ready`를 발행하고, 바로 짧은 효과음을 재생한 다음 마이크 녹음을 시작합니다.
즉 사용자는 효과음을 듣고 바로 질문하면 됩니다. 출력 장치를 직접 지정해야 하면
`QNA_READY_SOUND_OUTPUT_DEVICE`에 sounddevice 장치 번호나 장치명을 넣습니다.

## 로컬 셀프 테스트

MQTT 브로커 없이 페이로드 처리만 확인합니다.

```powershell
cd table\qna-server
$env:PYTHONPATH=".\src"
python -m qna_server --self-test
```

단위 테스트:

```powershell
$env:PYTHONPATH=".\src"
python -m unittest discover -s tests
```

## 구현 경계

- MQTT 흐름: `service.py`
- GMS Gemini direct/TTS 호출: `gms_client.py`
- 마이크 녹음: `speech.py`
- TTS wav 저장/재생: `tts.py`
- 룰북 로딩/context 구성: `knowledge.py`, `direct.py`
- VectorDB 인덱스: `vector_store.py`
- 답변 생성 오케스트레이션: `engine.py`

Spring 쪽에는 현재 실제 플레이 인원 저장 컬럼이 없으므로 `players`는 선택 값입니다.
값이 오면 답변 컨텍스트로 사용하고, 없어도 QnA 절차는 진행됩니다.
