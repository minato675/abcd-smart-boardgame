# 테스트 배포

현재 모델은 production용이 아니므로 `shadow` 환경에서만 테스트합니다.

## 1. 환경 준비

```bash
cd table/wakeword
./scripts/bootstrap.sh
```

For a new environment, run the bootstrap once from the project directory:

```bash
./scripts/bootstrap.sh
```

## 2. Shadow 설정 생성

`shadow.yaml`이 없으면 먼저 생성합니다.

```bash
cp config/development.yaml config/shadow.yaml
sed -i 's/^environment: development$/environment: shadow/' config/shadow.yaml
```

필요하면 `config/shadow.yaml`의 다음 값을 테스트 환경에 맞게 수정합니다.

```yaml
room_number: TEST_ROOM
device_id: test-wake-mic-01

mqtt:
  host: localhost
  port: 1883

audio:
  device: default
```

## 3. 설정 및 모델 검증

```bash
.venv/bin/python -m wakeword_module.manifest --config config/shadow.yaml --allow-unverified
```

정상 결과는 `ok: true`, `production_ready: false`,
`model_quality: unverified`입니다.

## 4. 모듈 실행

MQTT broker가 실행 중인지 확인한 뒤 실행합니다.

```bash
WAKEWORD_ALLOW_UNVERIFIED_MODELS=true .venv/bin/python -m wakeword_module --config config/shadow.yaml
```
```bash
WAKEWORD_ALLOW_UNVERIFIED_MODELS=true .venv/bin/python -m wakeword_module --config config/shadow.yaml --log-level DEBUG
```
종료하려면 `Ctrl+C`를 누릅니다.

상태 확인:

```bash
mosquitto_sub -h localhost -p 1883 -t /room/TEST_ROOM/wake/status -q 1
```

현재 모델과 phase-sweep 결과는 production 품질을 보장하지 않으므로,
실제 서비스 대신 테스트 장비와 테스트 MQTT room에서만 사용합니다.
